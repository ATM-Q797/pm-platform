"""项目列表与填报页的项目排序一致性（用户 2026-10-30 指令）。

要求：两个页面的项目顺序一一对应，统一按「项目计划开始时间」升序；
无计划日期的排最后；同日期按 id 升序。
"""
from __future__ import annotations

from datetime import date

from app.core.security import hash_password
from app.models import Project, User


def _mk(db, name: str, plan_start: date | None, market: str = "拉美区") -> Project:
    p = Project(
        code=f"ORD-{name}",
        category="新需求",
        name=name,
        owner="张三",
        market=market,
        status="进行中",
        plan_start=plan_start,
    )
    db.add(p)
    db.flush()
    return p


def _admin(db, username: str = "order_admin") -> User:
    u = User(username=username, name="排序管理员", role="admin",
             password_hash=hash_password("123456"), is_active=True,
             must_change_password=False)
    db.add(u)
    db.flush()
    return u


def test_both_pages_share_plan_start_order(client, db_session):
    """项目列表页与填报页返回的项目顺序一致，且按 plan_start 升序（None 最后）。"""
    _mk(db_session, "C-晚开始", date(2026, 9, 1))
    _mk(db_session, "A-早开始", date(2026, 3, 1))
    _mk(db_session, "D-无计划", None)
    _mk(db_session, "B-中开始", date(2026, 6, 1))

    admin = _admin(db_session)
    r = client.post("/api/auth/login", json={"username": admin.username, "password": "123456"})
    assert r.status_code == 200, r.text
    # 登录态走 Cookie（TestClient 自动携带），无需手动带 token

    r1 = client.get("/api/projects")
    assert r1.status_code == 200, r1.text
    rows1 = r1.json()

    r2 = client.get("/api/report/projects")
    assert r2.status_code == 200, r2.text
    rows2 = r2.json()

    ids1 = [p["id"] for p in rows1]
    ids2 = [p["id"] for p in rows2]
    assert ids1 == ids2, "两个页面的项目顺序必须一致"

    names = [p["name"] for p in rows1 if p["name"].startswith(("A-", "B-", "C-", "D-"))]
    assert names == ["A-早开始", "B-中开始", "C-晚开始", "D-无计划"], names
