"""日志配置模块。

在 FastAPI 应用启动时调用 setup_logging() 初始化日志格式。
生产环境输出 JSON 格式便于日志收集；开发环境输出可读文本。
"""
from __future__ import annotations

import logging
import os
import sys


def setup_logging():
    """初始化日志配置。"""
    app_env = os.environ.get("APP_ENV", "development")
    log_level = os.environ.get("LOG_LEVEL", "info").upper()

    if app_env == "production":
        # 生产：简洁格式，方便 docker logs / journald 收集
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    else:
        # 开发：详细格式，方便调试
        fmt = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=fmt,
        stream=sys.stdout,
        force=True,
    )

    # 降低第三方库日志级别，避免噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
