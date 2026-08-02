"""pytest 公共 fixture。

每个测试用独立的内存 SQLite 数据库，互不影响。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 让测试能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import database  # noqa: E402
from app import models  # noqa: E402,F401  (注册所有模型)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db_session():
    """内存数据库 Session，每个测试函数独立。

    使用 StaticPool 强制所有连接复用同一个底层连接，使内存库的表
    在 create_all 与后续 SessionLocal 请求间共享可见。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(conn, _):  # pragma: no cover
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient，注入测试 Session。"""
    # 清空导入报告全局状态，避免测试间污染
    from app.services import excel_importer
    excel_importer._set_last_report(None)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
