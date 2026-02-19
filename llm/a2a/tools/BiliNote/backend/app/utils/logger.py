import logging
import sys
from pathlib import Path
try:
    from utils import util
    _LOG_DIR = Path(util.ensure_log_dir("tools", "BiliNote"))
except Exception:
    _LOG_DIR = Path("logs")

# 日志目录
LOG_DIR = _LOG_DIR
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 控制台输出
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# 文件输出
file_handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
file_handler.setFormatter(formatter)

# 获取日志器

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.propagate = False
    return logger
