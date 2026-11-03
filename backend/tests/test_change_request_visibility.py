"""待审批列表的「我负责」口径（用户 2026-11-03 指令：朱全林看不到曹俊杰的申请）。

Excel 导入项目 managed_by 为空、owner 文本 = 负责人姓名——此前列表只认 managed_by，
负责人永远看不到待审批项（审批端点却是姓名回退口径，能批但看不见）。
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Phase, Project, Resource, User


def _login(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": "testpass"})
    assert r.status_code == 200, r.text


def test_owner_by_name_sees_pending_request(client: TestClient, db_session: Session):
    """Excel 导入项目（managed_by 空、owner 文本）的负责人能看到待审批项并批准。"""
    # 负责人：账号名 = 项目 owner 文本（Excel 导入口径），resource_id 为空亦可
    zhu = User(username="zqlin_t", name="朱全林", role="reporter",
               password_hash=hash_password("testpass"), must_change_password=False)
    db_session.add(zhu)
    # 阶段负责人曹俊杰（带 resource，阶段负责人判定需要）
    res = Resource(name="曹俊杰")
    db_session.add(res)
    db_session.flush()
    cao = User(username="cjjie_t", name="曹俊杰", role="reporter",
               password_hash=hash_password("testpass"), resource_id=res.id,
               must_change_password=False)
    db_session.add(cao)
    # Excel 导入形态的项目：managed_by=None、owner="朱全林"
    p = Project(code="CR-1", category="新需求", name="变更申请可见性项目",
                owner="朱全林", market="非洲区", status="进行中", managed_by=None)
    db_session.add(p)
    db_session.flush()
    ph = Phase(project_id=p.id, phase_type="P1", name="需求评估", sequence=1,
               plan_start=date(2026, 11, 1), plan_end=date(2026, 11, 10))
    ph.assignees.append(res)
    db_session.add(ph)
    db_session.commit()

    # 曹俊杰提交变更申请
    _login(client, "cjjie_t")
    r = client.post("/api/report/change-requests", json={
        "phase_id": ph.id,
        "plan_start": "2026-11-05", "plan_end": "2026-11-12",
    })
    assert r.status_code == 201, r.text

    # 修复点：朱全林（owner 文本匹配）能在待审批列表看到
    _login(client, "zqlin_t")
    pending = client.get("/api/report/change-requests").json()
    assert len(pending) == 1, pending
    assert pending[0]["phase_id"] == ph.id
    assert pending[0]["requester_name"] == "曹俊杰"

    # 且能批准（与审批端点同一口径，此前即通过——此处确保端到端）
    rv = client.post(f"/api/report/change-requests/{pending[0]['id']}/review",
                     json={"approved": True})
    assert rv.status_code == 200, rv.text
    assert rv.json()["status"] == "approved"


def test_non_owner_still_cannot_see_others_pending(client: TestClient, db_session: Session):
    """无关账号仍看不到别人的待审批项（口径收紧不能放水）。"""
    stranger = User(username="stranger_t", name="路人甲", role="reporter",
                    password_hash=hash_password("testpass"), must_change_password=False)
    res = Resource(name="路人甲")
    db_session.add(res)
    db_session.flush()
    db_session.add(stranger)
    p = Project(code="CR-2", category="新需求", name="无关人不可见项目",
                owner="朱全林", market="非洲区", status="进行中", managed_by=None)
    db_session.add(p)
    db_session.flush()
    ph = Phase(project_id=p.id, phase_type="P2", name="配置评估", sequence=1)
    ph.assignees.append(res)
    db_session.add(ph)
    db_session.commit()

    _login(client, "stranger_t")
    r = client.post("/api/report/change-requests", json={"phase_id": ph.id,
                                                         "plan_start": "2026-11-05"})
    assert r.status_code == 201, r.text

    _login(client, "stranger_t")
    assert client.get("/api/report/change-requests").json() == []
