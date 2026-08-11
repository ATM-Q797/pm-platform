"""Gunicorn 生产配置 — 使用 Uvicorn worker 运行 FastAPI。

启动命令：
    gunicorn app.main:app -c gunicorn_conf.py

环境变量：
    WORKERS        : worker 进程数（默认 4，建议 CPU 核数 * 2 + 1）
    BIND           : 绑定地址（默认 0.0.0.0:8000）
    LOG_LEVEL      : 日志级别（默认 info）
    ACCESS_LOG     : 是否开启访问日志（默认 true）
"""
from __future__ import annotations

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server Socket
# ---------------------------------------------------------------------------
bind = os.environ.get("BIND", "0.0.0.0:8000")

# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
# 默认 CPU 核数 * 2 + 1；可通过 WORKERS 环境变量覆盖
_default_workers = multiprocessing.cpu_count() * 2 + 1
workers = int(os.environ.get("WORKERS", str(_default_workers)))
worker_class = "uvicorn.workers.UvicornWorker"

# 超时：Gantt 图表等复杂接口可能较慢，给足时间
timeout = int(os.environ.get("WORKER_TIMEOUT", "120"))
graceful_timeout = 30

# Worker 自动重启（防止内存泄漏）
max_requests = 1000
max_requests_jitter = 50

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
loglevel = os.environ.get("LOG_LEVEL", "info")
accesslog = os.environ.get("ACCESS_LOG", "-")  # "-" = stdout
errorlog = "-"  # stderr

# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------
preload_app = True

# ---------------------------------------------------------------------------
# 安全：生产环境隐藏 server header
# ---------------------------------------------------------------------------
import gunicorn  # noqa: E402
gunicorn.SERVER = "pm-platform"
