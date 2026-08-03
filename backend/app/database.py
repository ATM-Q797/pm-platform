"""数据库连接与会话管理。

- 默认 PostgreSQL（Phase 5.0 起）；测试时可设 DATABASE_URL=sqlite:///:memory:
- 同步 SQLAlchemy 2.0 风格
- SQLite 连接额外开启 PRAGMA foreign_keys=ON（测试用）；PG 天然强制外键
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 默认连接本地 PostgreSQL（不指定用户，自动用系统用户；跨机器通用）；
# 可通过环境变量覆盖（如测试用 sqlite:///:memory:）
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/pm_platform",
)


def _create_engine() -> Engine:
    """创建 engine。SQLite 需要 check_same_thread=False；PG 无需特殊参数。"""
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False, future=True)

    # SQLite 默认不强制外键约束，测试时开启使级联删除生效；PG 天然强制，无需处理
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
