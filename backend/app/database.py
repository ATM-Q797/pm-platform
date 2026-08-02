"""数据库连接与会话管理。

- SQLite 单文件数据库（pm_platform.db）
- 同步 SQLAlchemy 2.0 风格
- 每个连接开启 PRAGMA foreign_keys=ON，使 ON DELETE CASCADE 生效
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 数据库文件路径：backend/pm_platform.db
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "pm_platform.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DB_PATH}")


def _create_engine() -> Engine:
    """创建 engine。SQLite 需要 check_same_thread=False 以支持 FastAPI 线程。"""
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False, future=True)

    # SQLite 默认不强制外键约束，这里在每次连接时开启，使级联删除生效
    if DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_connection, _connection_record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求分配一个 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """脚本/服务层使用：上下文管理器，提交或回滚自动处理。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
