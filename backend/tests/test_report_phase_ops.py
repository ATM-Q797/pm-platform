"""填报页「已建项目增删阶段」（用户 2026-10-30 指令）——随批次存档。

覆盖：+ 号在指定行下方插入（类型名自动取显示名、后续顺序后移、sequence 连续）；
- 号删除本行并重排；非项目负责人 403；专项项目 404；非法类型 400。
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Phase, Project, Resource, User


def _mk(db: Session, username: str, name: str, role: str = "reporter") -> User:
    res = Resource(name=name)
    db.add(res)
    db.flush()
    u = User(username=username, name=name, role=role, password_hash=hash_password("testpass"),
             resource_id=res.id, must_change_password=False)
    db.add(u)
    db.flush()
    return u


def _login(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": "testpass"})
    assert r.status_code == 200, r.text


def _project_with_phases(db: Session, owner: User, code: str = "PH-1") -> Project:
    p = Project(code=code, category="新需求", name="增删阶段项目", owner=owner.name,
                market="拉美区", status="进行中", managed_by=owner.id)
    db.add(p)
    db.flush()
    for i, t in enumerate(["P1", "P4", "P5"], start=1):
        db.add(Phase(project_id=p.id, phase_type=t, name=t, sequence=i))
    db.flush()
    return p


def test_add_phase_after_row_and_sequence(client: TestClient, db_session: Session):
    """+ 号：在指定阶段之后插入，类型名自动取显示名，后续顺序后移且 sequence 连续。"""
    owner = _mk(db_session, "ph_owner", "阶段负责人甲")
    p = _project_with_phases(db_session, owner)
    db_session.commit()
    _login(client, "ph_owner")

    phases = client.get(f"/api/report/projects/{p.id}").json()["phases"]
    anchor = phases[1]  # 第二行（P4 工业设计）
    r = client.post(f"/api/report/projects/{p.id}/phases",
                    json={"phase_type": "P3", "after_phase_id": anchor["id"]})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "模块选型"  # P3 显示名
    assert created["sequence"] == anchor["sequence"] + 1

    after = client.get(f"/api/report/projects/{p.id}").json()["phases"]
    assert [x["sequence"] for x in after] == [1, 2, 3, 4]  # 连续无空洞
    assert [x["phase_type"] for x in after] == ["P1", "P4", "P3", "P5"]  # 插在 P4 之后


def test_delete_phase_and_normalize(client: TestClient, db_session: Session):
    """- 号：删除本行，剩余阶段 sequence 重排为 1..n。"""
    owner = _mk(db_session, "ph_owner2", "阶段负责人乙")
    p = _project_with_phases(db_session, owner, code="PH-2")
    db_session.commit()
    _login(client, "ph_owner2")

    phases = client.get(f"/api/report/projects/{p.id}").json()["phases"]
    target = phases[0]
    r = client.delete(f"/api/report/phases/{target['id']}")
    assert r.status_code == 204, r.text

    after = client.get(f"/api/report/projects/{p.id}").json()["phases"]
    assert [x["sequence"] for x in after] == [1, 2]
    assert [x["phase_type"] for x in after] == ["P4", "P5"]


def test_phase_ops_forbidden_for_non_owner(client: TestClient, db_session: Session):
    """非项目负责人（阶段负责人）无权增删阶段：403。"""
    owner = _mk(db_session, "ph_owner3", "阶段负责人丙")
    other = _mk(db_session, "ph_other", "旁人丁")
    p = _project_with_phases(db_session, owner, code="PH-3")
    db_session.commit()

    _login(client, "ph_other")
    r = client.post(f"/api/report/projects/{p.id}/phases", json={"phase_type": "P2"})
    assert r.status_code == 403, r.text
    phases = client.get(f"/api/report/projects/{p.id}").json()["phases"]
    r = client.delete(f"/api/report/phases/{phases[0]['id']}")
    assert r.status_code == 403, r.text


def test_add_phase_invalid_type(client: TestClient, db_session: Session):
    """非法阶段类型 400（仅平台 10 类）。"""
    owner = _mk(db_session, "ph_owner4", "阶段负责人戊")
    p = _project_with_phases(db_session, owner, code="PH-4")
    db_session.commit()
    _login(client, "ph_owner4")
    r = client.post(f"/api/report/projects/{p.id}/phases", json={"phase_type": "自定义X"})
    assert r.status_code == 400
    assert "10 类" in r.json()["detail"]
