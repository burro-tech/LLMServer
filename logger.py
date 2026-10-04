import logging
import os
import sys
from datetime import datetime, timedelta
from pytz import timezone
from logging.handlers import RotatingFileHandler

MAX_BYTES = 1 * 1024 * 1024 * 1024   # 1 GB

logger = logging.getLogger()

def __path(path, file):
    if file is None:
        return path
    return os.path.join(path, file)

def log_path(file=None):
    return __path(r'./log', file)

def get_time(granularity='d'):
    fmt = '%Y-%m-%d'
    if 'S' in granularity:
        fmt = '%Y-%m-%d %H:%M:%S'
    elif 'm' in granularity:
        fmt = '%Y%m%d.%H%M%S.%f'
    eastern = timezone('US/Eastern')
    loc_dt = datetime.now(eastern)
    # print("Current time in Eastern is", loc_dt.strftime(fmt))

    return loc_dt.strftime(fmt)


def init_logger(name):
    global logger
    logger.name = name
    logger.setLevel(logging.DEBUG)
    sys.stdout.reconfigure(encoding='utf-8')
    # fh = logging.FileHandler(log_path(f'{name}_{get_time()}.log'),encoding='utf-8')
    fh = RotatingFileHandler(
        log_path(f'{name}_{get_time()}.log'),
        maxBytes=MAX_BYTES,
        backupCount=2,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)

    # 创建一个用于输出到控制台的处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.set_name('console')

    # 创建一个格式化器并将其添加到处理器
    formatter = logging.Formatter('%(levelname)s %(threadName)s - %(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    # 将处理器添加到日志记录器
    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger
