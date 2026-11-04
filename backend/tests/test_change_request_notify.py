"""二期④（旧入口作废下沉）+ 二期①（我的申请 / 站内通知）——随批次存档。

覆盖：
- 旧入口（PUT /api/phases/{id}）直改计划时间 → pending 申请自动作废（此前只会被批准回滚）
- 填报页（PATCH /api/report/phases/{id}）直改 → 同样作废，且申请人收到通知
- 提交申请 → 项目负责人收到通知；批准/驳回 → 申请人收到通知（驳回带原因）
- 「我的申请」列表：申请人看到状态、驳回原因、审批人
- 通知未读数 / 已读 / 越权访问他人通知 404
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Notification, Phase, PhaseChangeRequest, Project, Resource, User


def _user(db: Session, username: str, name: str, role: str,
          resource_id: int | None = None) -> User:
    u = User(username=username, name=name, role=role,
             password_hash=hash_password("testpass"), resource_id=resource_id,
             must_change_password=False)
    db.add(u)
    db.flush()
    return u


def _login(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": "testpass"})
    assert r.status_code == 200, r.text


def _fixture(db: Session, *, managed: bool = True) -> tuple[User, User, Project, Phase]:
    """项目负责人（manager）+ 阶段负责人（engineer）+ 一个带计划时间的阶段。"""
    owner = _user(db, "mgr_owner", "朱全林", "manager")
    res = Resource(name="曹俊杰")
    db.add(res)
    db.flush()
    req = _user(db, "eng_req", "曹俊杰", "engineer", resource_id=res.id)
    project = Project(code="CR-N1", category="新需求", name="作废钩子项目",
                      owner="朱全林", market="非洲区", status="进行中",
                      managed_by=owner.id if managed else None)
    db.add(project)
    db.flush()
    phase = Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1,
                  plan_start=date(2026, 11, 1), plan_end=date(2026, 11, 10))
    phase.assignees.append(res)
    db.add(phase)
    db.commit()
    return owner, req, project, phase


def _submit(client: TestClient, phase_id: int) -> dict:
    _login(client, "eng_req")
    r = client.post("/api/report/change-requests",
                    json={"phase_id": phase_id, "plan_start": "2026-11-05"})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- 二期④：两个入口都作废 ----------

def test_old_page_direct_edit_invalidates_pending(client: TestClient, db_session: Session):
    """旧入口（项目详情页 PUT /api/phases）直改计划时间 → pending 自动作废。

    这条修复的核心：修复前旧入口改完日期，申请仍 pending，谁再点「批准」
    apply_change_proposal 会把日期写回旧提案（数据被回滚）。
    """
    _owner, _req, _p, phase = _fixture(db_session)
    req = _submit(client, phase.id)

    _login(client, "mgr_owner")
    r = client.put(f"/api/phases/{phase.id}", json={"plan_start": "2026-11-10"})
    assert r.status_code == 200, r.text
    assert r.json()["plan_start"] == "2026-11-10"

    db_session.expire_all()
    row = db_session.get(PhaseChangeRequest, req["id"])
    assert row.status == "rejected", row.status
    assert row.review_comment == "负责人已直接改期，申请作废"

    # 申请人收到「被作废」通知
    notes = db_session.scalars(
        select(Notification).where(Notification.type == "change_request_invalidated")
    ).all()
    assert len(notes) == 1
    assert notes[0].user_id == row.requested_by

    # 关键回归：批准接口已无法再回滚（申请已非 pending）
    r = client.post(f"/api/report/change-requests/{req['id']}/review", json={"approved": True})
    assert r.status_code == 400


def test_report_page_direct_edit_invalidates_and_notifies(client: TestClient, db_session: Session):
    """填报页（PATCH /api/report/phases）直改计划时间 → 同样作废并通知（原规则未回归）。"""
    _owner, _req, _p, phase = _fixture(db_session)
    req = _submit(client, phase.id)

    _login(client, "mgr_owner")
    r = client.patch(f"/api/report/phases/{phase.id}", json={"plan_end": "2026-11-20"})
    assert r.status_code == 200, r.text

    db_session.expire_all()
    row = db_session.get(PhaseChangeRequest, req["id"])
    assert row.status == "rejected"
    assert db_session.scalars(
        select(Notification).where(Notification.type == "change_request_invalidated")
    ).first() is not None


# ---------- 二期①：通知 + 我的申请 ----------

def test_submit_and_review_send_notifications(client: TestClient, db_session: Session):
    """提交 → 负责人收到通知；驳回 → 申请人收到带原因的通知。"""
    owner, req_user, _p, phase = _fixture(db_session)
    req = _submit(client, phase.id)

    db_session.expire_all()
    notes = db_session.scalars(
        select(Notification).where(Notification.user_id == owner.id)).all()
    assert len(notes) == 1
    assert notes[0].type == "change_request_created"
    assert "曹俊杰" in notes[0].title + (notes[0].body or "")

    # 负责人驳回
    _login(client, "mgr_owner")
    r = client.post(f"/api/report/change-requests/{req['id']}/review",
                    json={"approved": False, "comment": "这段时间排不开"})
    assert r.status_code == 200, r.text

    db_session.expire_all()
    notes = db_session.scalars(
        select(Notification).where(Notification.user_id == req_user.id)).all()
    assert len(notes) == 1
    assert notes[0].type == "change_request_rejected"
    assert "这段时间排不开" in (notes[0].body or "")


def test_my_change_requests_shows_status_and_reason(client: TestClient, db_session: Session):
    """「我的申请」：申请人看到状态、驳回原因、审批人——此前完全没有这个入口。"""
    _owner, _req_user, _p, phase = _fixture(db_session)
    req = _submit(client, phase.id)

    _login(client, "mgr_owner")
    client.post(f"/api/report/change-requests/{req['id']}/review",
                json={"approved": False, "comment": "先做别的"})

    _login(client, "eng_req")
    rows = client.get("/api/report/my-change-requests").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "rejected"
    assert row["review_comment"] == "先做别的"
    assert row["reviewer_name"] == "朱全林"
    assert row["phase_name"] == "需求评估"
    assert row["project_name"] == "作废钩子项目"


def test_notification_read_flow_and_ownership(client: TestClient, db_session: Session):
    """未读数 → 单条已读 → 全部已读；越权标记他人通知一律 404。"""
    owner, _req_user, _p, phase = _fixture(db_session)
    first = _submit(client, phase.id)

    _login(client, "mgr_owner")
    assert client.get("/api/report/notifications/unread-count").json()["count"] == 1
    notes = client.get("/api/report/notifications").json()
    assert len(notes) == 1
    nid = notes[0]["id"]

    # 他人（申请人）标记这条通知 → 404，不泄露存在性
    _login(client, "eng_req")
    assert client.post(f"/api/report/notifications/{nid}/read").status_code == 404

    _login(client, "mgr_owner")
    assert client.post(f"/api/report/notifications/{nid}/read").status_code == 204
    assert client.get("/api/report/notifications/unread-count").json()["count"] == 0

    # 先把首个申请审掉（单 pending 语义），再产生一条新申请 → 全部已读
    client.post(f"/api/report/change-requests/{first['id']}/review", json={"approved": True})
    _login(client, "eng_req")
    r = client.post("/api/report/change-requests", json={"phase_id": phase.id, "plan_end": "2026-11-15"})
    assert r.status_code == 201, r.text
    _login(client, "mgr_owner")
    assert client.get("/api/report/notifications/unread-count").json()["count"] == 1
    assert client.post("/api/report/notifications/read-all").status_code == 204
    assert client.get("/api/report/notifications/unread-count").json()["count"] == 0


# ---------- 评审 #1 的回归：误作废、姓名回退、旧工程师流 ----------

def test_unchanged_plan_save_does_not_invalidate(client: TestClient, db_session: Session):
    """只改进度（payload 仍带原计划时间）不得误废申请——评审 #1 🔴1。

    PhaseEditor 每次保存都会带上 plan_start/plan_end，若按「字段出现」判定，
    负责人只改进度就会销毁申请人的待审申请并发一条不实通知。
    """
    _owner, _req, _p, phase = _fixture(db_session)
    req = _submit(client, phase.id)

    _login(client, "mgr_owner")
    r = client.put(f"/api/phases/{phase.id}", json={
        "plan_start": "2026-11-01",  # 与现值相同
        "plan_end": "2026-11-10",    # 与现值相同
        "progress": 40,
    })
    assert r.status_code == 200, r.text

    db_session.expire_all()
    row = db_session.get(PhaseChangeRequest, req["id"])
    assert row.status == "pending", f"计划未变却把申请作废了：{row.review_comment}"
    assert db_session.scalars(
        select(Notification).where(Notification.type == "change_request_invalidated")
    ).all() == []


def test_owner_by_name_receives_notification(client: TestClient, db_session: Session):
    """Excel 导入项目（managed_by 空）按姓名找到负责人并通知——评审 #1 🔵9。"""
    owner, _req_user, project, phase = _fixture(db_session, managed=False)
    assert project.managed_by is None and project.owner == owner.name
    _submit(client, phase.id)

    db_session.expire_all()
    notes = db_session.scalars(
        select(Notification).where(Notification.type == "change_request_created")).all()
    assert len(notes) == 1
    assert notes[0].user_id == owner.id


def test_legacy_engineer_flow_sends_notifications(client: TestClient, db_session: Session):
    """旧工程师流（/api/phase-change-requests 提交 + review 审批）同样发通知——评审 #1 🟡2。"""
    owner, req_user, _p, phase = _fixture(db_session)

    _login(client, "eng_req")
    r = client.post("/api/phase-change-requests",
                    json={"phase_id": phase.id, "proposed_changes": {"plan_end": "2026-11-20"}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    db_session.expire_all()
    notes = db_session.scalars(
        select(Notification).where(Notification.user_id == owner.id)).all()
    assert len(notes) == 1 and notes[0].type == "change_request_created"

    _login(client, "mgr_owner")
    rv = client.post(f"/api/phase-change-requests/{rid}/review",
                     json={"approved": True, "comment": None})
    assert rv.status_code == 200, rv.text

    db_session.expire_all()
    notes = db_session.scalars(
        select(Notification).where(Notification.user_id == req_user.id)).all()
    assert len(notes) == 1 and notes[0].type == "change_request_approved"

