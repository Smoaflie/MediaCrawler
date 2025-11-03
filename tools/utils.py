# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import argparse
import logging

from .crawler_util import *
from .slider_util import *
from .time_util import *

def init_loging_config(log_dir="logs", log_name="media_crawler.log", debug_to_file=False):
    """
    初始化日志配置
    :param log_dir: 日志保存目录
    :param log_name: 日志文件名
    :param debug_to_file: 是否将文件日志级别设为 DEBUG（True）或 INFO（False）
    :return: logger 实例
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_name)

    # ===== 日志格式 =====
    fmt = "%(asctime)s %(name)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    # ===== 控制台Handler（仅输出INFO及以上）=====
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # ===== 文件Handler（输出DEBUG或INFO）=====
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG if debug_to_file else logging.INFO)
    file_handler.setFormatter(formatter)

    # ===== 获取logger =====
    logger = logging.getLogger("MediaCrawler")
    logger.setLevel(logging.DEBUG)  # 最高等级，以便子handler自行过滤
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = init_loging_config(debug_to_file=True)

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
