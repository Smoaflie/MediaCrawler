# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import asyncio
import functools
import sys
import threading
from typing import Optional

from playwright.async_api import BrowserContext, Page
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

import config
from base.base_crawler import AbstractLogin
from cache.cache_factory import CacheFactory
from tools import utils

class Xpath:
    LOGIN_BUTTON = "xpath=//*[@id='app']/div[1]/div[2]/div[1]/ul/div[1]//button"
    QRCODE_IMG_SELECTOR = "xpath=//img[@class='qrcode-img']"
    AGREE_PRIVACY_ELE = "xpath=//div[@class='agreements']/span"

class XiaoHongShuLogin(AbstractLogin):

    def __init__(self,
                 login_type: str,
                 browser_context: BrowserContext,
                 context_page: Page,
                 login_phone: Optional[str] = "",
                 cookie_str: str = ""
                 ):
        config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.cookie_str = cookie_str
        self._qrcode_close_event: Optional[threading.Event] = None
        self._qrcode_displaying: bool = False

    def _signal_close_qrcode_window(self) -> None:
        """Signal QR window to close if it's open."""
        if self._qrcode_close_event:
            self._qrcode_close_event.set()
        self._qrcode_close_event = None
        self._qrcode_displaying = False

    async def _display_qrcode(self, refresh: bool = True) -> None:
        """
        Show QR code in a window (reused for initial + secondary verification).
        Set refresh=True to force reopening with latest QR.
        """
        if refresh:
            self._signal_close_qrcode_window()
            self._qrcode_displaying = False
        if self._qrcode_displaying:
            return

        base64_qrcode_img = await utils.find_login_qrcode(
            self.context_page,
            selector=Xpath.QRCODE_IMG_SELECTOR
        )
        if not base64_qrcode_img:
            utils.logger.error("[XiaoHongShuLogin] 未获取到二维码，无法展示")
            return

        self._qrcode_close_event = threading.Event()
        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img, self._qrcode_close_event)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)
        self._qrcode_displaying = True

    async def _log_validation_prompts(self, page_content: str) -> bool:
        """Log hints when extra verification/scan is requested."""
        if "请通过验证" in page_content:
            utils.logger.info("[XiaoHongShuLogin.check_login_state] 登录过程中出现验证码，请手动验证")
            return True
        if "扫码验证" in page_content:
            utils.logger.info("[XiaoHongShuLogin.check_login_state] 登录过程中出现扫码验证，请二次验证")
            await self._display_qrcode()
            return True
        return False

    async def _qr_validation_success(self) -> bool:
        """
        Detect the toast/text '验证成功' to confirm QR scan without nested waits.
        Uses a short selector wait to listen for the event.
        """
        try:
            await self.context_page.wait_for_selector("text=验证成功", timeout=60000)
            return True
        except PlaywrightTimeoutError:
            return False

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self, no_logged_in_session: str) -> bool:
        """
            Check if the current login status is successful and return True otherwise return False
            retry decorator will retry 20 times if the return value is False, and the retry interval is 1 second
            if max retry times reached, raise RetryError
        """

        while await self._log_validation_prompts(await self.context_page.content()):
            if await self._qr_validation_success():
                utils.logger.info("[XiaoHongShuLogin.check_login_state] 检测到二维码验证成功提示")
                self._signal_close_qrcode_window()
                await asyncio.sleep(5)
            
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        current_web_session = cookie_dict.get("web_session")
        if current_web_session != no_logged_in_session:
            return True
        return False

    async def begin(self):
        """Start login xiaohongshu"""
        utils.logger.info("[XiaoHongShuLogin.begin] Begin login xiaohongshu ...")
        if config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[XiaoHongShuLogin.begin]I nvalid Login Type Currently only supported qrcode or phone or cookies ...")

    async def login_by_mobile(self):
        """Login xiaohongshu by mobile"""
        utils.logger.info("[XiaoHongShuLogin.login_by_mobile] Begin login xiaohongshu by mobile ...")
        await asyncio.sleep(1)
        if not "手机号登录" in await self.context_page.content():
            try:
                # 小红书进入首页后，有可能不会自动弹出登录框，需要手动点击登录按钮
                login_button_ele = await self.context_page.wait_for_selector(
                selector=Xpath.LOGIN_BUTTON,
                timeout=5000
                )
                await login_button_ele.click()
            except PlaywrightTimeoutError:
                utils.logger.error("[XiaoHongShuLogin.login_by_mobile] login button not found, stop ...")
                sys.exit()

        await asyncio.sleep(1)
        login_container_ele = await self.context_page.wait_for_selector("div.login-container")
        input_ele = await login_container_ele.query_selector("label.phone > input")
        await input_ele.fill(self.login_phone)
        await asyncio.sleep(1.5)

        send_btn_ele = await login_container_ele.query_selector("label.auth-code > span")
        await send_btn_ele.click()  # 点击发送验证码
        while await send_btn_ele.text_content() and "重新发送" not in await send_btn_ele.text_content():
            utils.logger.info("[XiaoHongShuLogin.login_by_mobile] send sms code button is disabled, wait for 1 second ...")
            await asyncio.sleep(1)
            await send_btn_ele.click()  # 点击发送验证码
        sms_code_input_ele = await login_container_ele.query_selector("label.auth-code > input")
        submit_btn_ele = await login_container_ele.query_selector("div.input-container form > button")
        cache_client = CacheFactory.create_cache(config.CACHE_TYPE_MEMORY)
        max_get_sms_code_time = 60 * 3  # 最长获取验证码的时间为2分钟
        no_logged_in_session = ""
        while max_get_sms_code_time > 0:
            utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] get sms code from cache_client remaining time {max_get_sms_code_time}s ...")
            await asyncio.sleep(1)
            sms_code_key = f"xhs_{self.login_phone}"
            sms_code_value = cache_client.get(sms_code_key)
            if not sms_code_value:
                max_get_sms_code_time -= 1
                continue

            sms_code_text = sms_code_value.decode() if isinstance(sms_code_value, (bytes, bytearray)) else str(sms_code_value)
            utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] get sms code from cache_client success sms_code is {sms_code_text} ...")

            current_cookie = await self.browser_context.cookies()
            _, cookie_dict = utils.convert_cookies(current_cookie)
            no_logged_in_session = cookie_dict.get("web_session")

            await sms_code_input_ele.fill(value=sms_code_text)  # 输入短信验证码
            await asyncio.sleep(0.5)
            agree_privacy_ele = self.context_page.locator(Xpath.AGREE_PRIVACY_ELE)
            await agree_privacy_ele.click()  # 点击同意隐私协议
            await asyncio.sleep(1.5)

            await submit_btn_ele.click()  # 点击登录

            # todo ... 应该还需要检查验证码的正确性有可能输入的验证码不正确
            break

        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            utils.logger.info("[XiaoHongShuLogin.login_by_mobile] Login xiaohongshu failed by mobile login method ...")
            sys.exit()

        wait_redirect_seconds = 5
        utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    async def login_by_qrcode(self):
        """login xiaohongshu website and keep webdriver login state"""
        utils.logger.info("[XiaoHongShuLogin.login_by_qrcode] Begin login xiaohongshu by qrcode ...")

        await asyncio.sleep(1)
        if not "手机号登录" in await self.context_page.content():
            try:
                # if this website does not automatically popup login dialog box, we will manual click login button
                login_button_ele = await self.context_page.wait_for_selector(
                selector=Xpath.LOGIN_BUTTON,
                timeout=5000
                )
                await login_button_ele.click()
            except PlaywrightTimeoutError:
                utils.logger.error("[XiaoHongShuLogin.login_by_mobile] login button not found, stop ...")
                sys.exit()
        # login_selector = "div.login-container > div.left > div.qrcode > img"
        qrcode_img_selector = Xpath.QRCODE_IMG_SELECTOR
        # find login qrcode
        base64_qrcode_img = await utils.find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            utils.logger.error("[XiaoHongShuLogin.login_by_qrcode] login failed , have not found qrcode please check ....")
            sys.exit()

        # get not logged session
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        no_logged_in_session = cookie_dict.get("web_session")

        # show login qrcode
        # fix issue #12
        # we need to use partial function to call show_qrcode function and run in executor
        # then current asyncio event loop will not be blocked
        await self._display_qrcode()

        utils.logger.info(f"[XiaoHongShuLogin.login_by_qrcode] waiting for scan code login, remaining time is 120s")
        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            utils.logger.info("[XiaoHongShuLogin.login_by_qrcode] Login xiaohongshu failed by qrcode login method ...")
            self._signal_close_qrcode_window()
            sys.exit()
        finally:
            # signal qrcode window to close (if still open)
            self._signal_close_qrcode_window()

        wait_redirect_seconds = 5
        utils.logger.info(f"[XiaoHongShuLogin.login_by_qrcode] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    async def login_by_cookies(self):
        """login xiaohongshu website by cookies"""
        utils.logger.info("[XiaoHongShuLogin.login_by_cookies] Begin login xiaohongshu by cookie ...")
        for key, value in utils.convert_str_cookie_to_dict(self.cookie_str).items():
            if key != "web_session":  # only set web_session cookie attr
                continue
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".xiaohongshu.com",
                'path': "/"
            }])
