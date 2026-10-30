"""信息填报一期：角色封锁矩阵 + 身份判定/字段级权限单测（随批次存档）。

覆盖设计 §八：
- reporter 封锁矩阵（RT-5 对应单测面）：既有 /api/* 全 403，/api/report/*、/api/auth/* 放行
- §3.2 三身份字段级 editable / PATCH 越权 403 附字段名
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Phase,
    Project,
    Resource,
    User,
    phase_assignee,
)


def _mk_user(db: Session, username: str, role: str, name: str = "测试用户",
             resource_id: int | None = None) -> User:
    u = User(username=username, name=name, role=role,
             password_hash=hash_password("testpass"), resource_id=resource_id,
             must_change_password=False)
    db.add(u)
    db.flush()
    return u


def _login(client: TestClient, username: str) -> None:
    resp = client.post("/api/auth/login", json={"username": username, "password": "testpass"})
    assert resp.status_code == 200, resp.text


# ---------- RT-5：reporter 封锁矩阵 ----------

def test_reporter_lockdown_matrix(client: TestClient, db_session: Session):
    """reporter 登录 → 既有任意 /api/* 全 403；/api/report/* 与 /api/auth/* 放行。"""
    _mk_user(db_session, "rep_lock", "reporter", "填报人甲")
    db_session.commit()
    _login(client, "rep_lock")

    blocked = [
        ("get", "/api/projects"),
        ("get", "/api/projects/1"),
        ("post", "/api/projects"),
        ("get", "/api/phases/1"),
        ("put", "/api/phases/1"),
        ("get", "/api/resources"),
        ("get", "/api/resources/heatmap"),
        ("get", "/api/users"),
        ("post", "/api/users"),
        ("get", "/api/dashboard/stats"),
        ("get", "/api/export/excel"),
        ("post", "/api/import/preview"),
        ("get", "/api/phase-change-requests"),
        ("post", "/api/phase-change-requests"),
        ("get", "/api/delete-requests"),
        ("get", "/api/operation-logs"),
        ("get", "/api/templates"),
        ("get", "/api/analysis/trend"),
        ("post", "/api/analysis/snapshots/run"),
    ]
    for method, url in blocked:
        resp = client.request(method.upper(), url, json={})
        assert resp.status_code == 403, f"{method.upper()} {url} 应封锁，实际 {resp.status_code}"

    # 放行面：report 8 接口可达（业务校验另测，这里只验证不被封锁门拦截）
    assert client.get("/api/report/projects").status_code == 200
    assert client.get("/api/report/meta").status_code == 200
    assert client.get("/api/report/change-requests").status_code == 200
    # auth 面：me 可达
    assert client.get("/api/auth/me").status_code == 200


def test_non_reporter_not_blocked(client: TestClient, db_session: Session):
    """封锁门只作用于 reporter——engineer 仍可访问既有接口。"""
    _mk_user(db_session, "eng_lock", "engineer", "工程师甲")
    db_session.commit()
    _login(client, "eng_lock")
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/report/projects").status_code == 200


def test_anonymous_unaffected_by_gate(client: TestClient):
    """未登录请求不被封锁门改变行为（无鉴权接口照旧可达，如 resources）。

    TestClient 随 conftest 自动登录带 admin Cookie——先清 Cookie 再模拟匿名。
    """
    client.cookies.clear()
    assert client.get("/api/resources").status_code == 200
    # 原本要登录的接口：匿名 401（门不改变既有鉴权语义）
    resp = client.get("/api/projects")
    assert resp.status_code == 401


# ---------- §3.2 身份判定与字段级权限 ----------

def _fixture_owner_assignee_other(db_session: Session):
    """负责人 + 阶段负责人 + 路人 各一，项目/阶段各一。"""
    owner = _mk_user(db_session, "rep_owner", "reporter", "负责人甲")
    assignee = _mk_user(db_session, "rep_assignee", "reporter", "阶段负责人乙")
    other = _mk_user(db_session, "rep_other", "reporter", "路人丙")
    res = Resource(name="阶段负责人乙")
    db_session.add(res)
    db_session.flush()
    assignee.resource_id = res.id
    project = Project(code="9001", category="新需求", name="填报测试项目", owner="负责人甲",
                      market="拉美区", status="进行中", managed_by=owner.id)
    db_session.add(project)
    db_session.flush()
    phase = Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1,
                  plan_start=date.today(), plan_end=date.today() + timedelta(days=7),
                  status="进行中", progress=40)
    db_session.add(phase)
    db_session.flush()
    db_session.execute(phase_assignee.insert().values(phase_id=phase.id, resource_id=res.id))
    db_session.commit()
    return owner, assignee, other, project, phase


def test_owner_editable_all_fields(client: TestClient, db_session: Session):
    """负责人：项目级 + 阶段全部字段 editable（含 plan_* 直改）。

    例外（用户 2026-10-29 权限分级需求 2）：负责人字段固定，managed_by 仅 admin
    可改——owner 的 editable.managed_by 为 False 是预期行为。
    """
    owner, _a, _o, project, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_owner")
    detail = client.get(f"/api/report/projects/{project.id}").json()
    assert detail["is_mine"] is True
    assert all(v for k, v in detail["editable"].items() if k != "managed_by")
    assert detail["editable"]["managed_by"] is False
    row = next(p for p in detail["phases"] if p["id"] == phase.id)
    assert all(row["editable"].values())
    assert row["can_request_change"] is False


def test_assignee_field_level_editable(client: TestClient, db_session: Session):
    """阶段负责人：actual/status/progress/remark/assignee_ids 可改；plan_* 只读 + 可申请。"""
    _o, assignee, _x, project, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_assignee")
    detail = client.get(f"/api/report/projects/{project.id}").json()
    row = next(p for p in detail["phases"] if p["id"] == phase.id)
    assert row["editable"]["actual_start"] is True
    assert row["editable"]["status"] is True
    assert row["editable"]["progress"] is True
    assert row["editable"]["plan_start"] is False
    assert row["editable"]["plan_end"] is False
    assert row["can_request_change"] is True
    # 项目级：非负责人全 False
    assert not any(detail["editable"].values())


def test_patch_forbidden_field_403_with_field_name(client: TestClient, db_session: Session):
    """PATCH 越权字段：整请求 403 且附字段名（RT-2 后端面）。"""
    _o, _a, _x, _p, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_assignee")
    resp = client.patch(f"/api/report/phases/{phase.id}", json={"plan_start": "2026-11-01"})
    assert resp.status_code == 403
    assert "plan_start" in resp.json()["detail"]
    # 整请求不落库：合法字段混入越权字段也全部不生效
    resp2 = client.patch(f"/api/report/phases/{phase.id}",
                         json={"progress": 60, "plan_start": "2026-11-01"})
    assert resp2.status_code == 403
    db_session.refresh(phase)
    assert phase.progress == 40


def test_viewer_role_readonly(client: TestClient, db_session: Session):
    """路人（非负责人非阶段负责人）：PATCH 全字段 403。"""
    _o, _a, other, _p, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_other")
    resp = client.patch(f"/api/report/phases/{phase.id}", json={"remark": "偷改"})
    assert resp.status_code == 403
    db_session.refresh(phase)
    assert phase.remark is None


def test_owner_direct_edit_invalidates_pending(client: TestClient, db_session: Session):
    """负责人直改 plan_* → pending 申请自动 rejected，comment 固定（RT-4 后端面）。"""
    from app.models import PhaseChangeRequest
    owner, assignee, _o2, project, phase = _fixture_owner_assignee_other(db_session)
    req = PhaseChangeRequest(phase_id=phase.id, project_id=project.id,
                             requested_by=assignee.id, status="pending",
                             proposed_changes='{"plan_start": {"old": null, "new": "2026-12-01"}}')
    db_session.add(req)
    db_session.commit()
    _login(client, "rep_owner")
    resp = client.patch(f"/api/report/phases/{phase.id}",
                        json={"plan_start": "2026-11-15", "plan_end": "2026-11-20"})
    assert resp.status_code == 200, resp.text
    db_session.refresh(req)
    assert req.status == "rejected"
    assert req.review_comment == "负责人已直接改期，申请作废"
    assert str(phase.plan_start) == "2026-11-15"


def test_assignee_cannot_patch_assignee_ids(client: TestClient, db_session: Session):
    """assignee_ids 指派是项目负责人专属（设计 §二/验收 8）：阶段负责人 PATCH → 403 附字段名。

    评审发现修复回归：修复前 editable 声明 True + check 放行 + 路由静默丢弃（200 无效）。
    """
    _o, assignee, _x, project, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_assignee")
    resp = client.patch(f"/api/report/phases/{phase.id}", json={"assignee_ids": [999]})
    assert resp.status_code == 403
    assert "assignee_ids" in resp.json()["detail"]
    # editable 下发也不得声明 True
    detail = client.get(f"/api/report/projects/{project.id}").json()
    row = next(p for p in detail["phases"] if p["id"] == phase.id)
    assert row["editable"]["assignee_ids"] is False
    assert row["editable"]["status"] is True  # 阶段负责人合法字段不受影响
    # 负责人仍可指派
    _login(client, "rep_owner")
    ok = client.patch(f"/api/report/phases/{phase.id}", json={"assignee_ids": []})
    assert ok.status_code == 200


def test_change_request_inverted_range_blocked(client: TestClient, db_session: Session):
    """倒挂区间防护覆盖申请路径（评审残留 🔵 补齐）：提交 400；批准时现值漂移再拦。"""
    _o, assignee, _x, _p, phase = _fixture_owner_assignee_other(db_session)
    _login(client, "rep_assignee")
    # 单字段 plan_end 早于库内 plan_start → 400
    resp = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_end": "2020-01-01"})
    assert resp.status_code == 400
    assert "倒挂" in resp.json()["detail"] or "早于" in resp.json()["detail"]
    # 两字段倒挂 → 400
    resp = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-12-10", "plan_end": "2026-12-01"})
    assert resp.status_code == 400
