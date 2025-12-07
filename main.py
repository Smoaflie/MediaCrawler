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
import os
import sys
import threading
from typing import Optional

import cmd_arg
import config
from database import db
from base.base_crawler import AbstractCrawler
from media_platform.bilibili import BilibiliCrawler
from media_platform.douyin import DouYinCrawler
from media_platform.kuaishou import KuaishouCrawler
from media_platform.tieba import TieBaCrawler
from media_platform.weibo import WeiboCrawler
from media_platform.xhs import XiaoHongShuCrawler
from media_platform.zhihu import ZhihuCrawler
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var


class CrawlerFactory:
    CRAWLERS = {
        "xhs": XiaoHongShuCrawler,
        "dy": DouYinCrawler,
        "ks": KuaishouCrawler,
        "bili": BilibiliCrawler,
        "wb": WeiboCrawler,
        "tieba": TieBaCrawler,
        "zhihu": ZhihuCrawler,
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform Currently only supported xhs or dy or ks or bili ..."
            )
        return crawler_class()


crawler: Optional[AbstractCrawler] = None



def _start_internal_sms_api():
    """
    Optional lightweight FastAPI server (same process) to push sms codes into memory cache.
    Enable by setting MEDIA_CRAWLER_ENABLE_SMS_API=1 before running main.py.
    """
    if config.os.getenv("MEDIA_CRAWLER_ENABLE_SMS_API") != "1" and config.base_config.LOGIN_TYPE != "phone":
        return None
    try:
        import uvicorn
        from recv_sms import app
    except Exception as e:  # pragma: no cover - best effort helper
        print(f"Failed to start internal sms api: {e}")
        return None

    host = os.getenv("MEDIA_CRAWLER_SMS_API_HOST", "127.0.0.1")
    port = int(os.getenv("MEDIA_CRAWLER_SMS_API_PORT", "8899"))
    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": host,
            "port": port,
            "log_level": "warning",
            "access_log": False,
        },
        daemon=True,
    )
    thread.start()
    print(f"Internal sms api started at http://{host}:{port}/cache/sms-code")
    return thread

# persist-1<persist1@126.com>
# 原因：增加 --init_db 功能，用于数据库初始化。
# 副作用：无
# 回滚策略：还原此文件。
async def main():
    # Init crawler
    global crawler

    # parse cmd
    args = await cmd_arg.parse_cmd()

    # init db
    if args.init_db:
        await db.init_db(args.init_db)
        print(f"Database {args.init_db} initialized successfully.")
        return  # Exit the main function cleanly

    _start_internal_sms_api()

    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()

    # Generate wordcloud after crawling is complete
    # Only for JSON save mode
    if config.SAVE_DATA_OPTION == "json" and config.ENABLE_GET_WORDCLOUD:
        try:
            file_writer = AsyncFileWriter(
                platform=config.PLATFORM,
                crawler_type=crawler_type_var.get()
            )
            await file_writer.generate_wordcloud_from_comments()
        except Exception as e:
            print(f"Error generating wordcloud: {e}")


def cleanup():
    if crawler:
        # asyncio.run(crawler.close())
        pass
    if config.SAVE_DATA_OPTION in ["db", "sqlite"]:
        asyncio.run(db.close())


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    finally:
        import tkinter as tk
        from tkinter import messagebox

        # 创建主窗口（隐藏，不显示）
        root = tk.Tk()
        root.withdraw()

        # 显示提示弹窗
        root.attributes('-topmost', True)
        messagebox.showinfo("提示", "MediaCrawler已终止！", parent=root)
        cleanup()
