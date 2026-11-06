"""过程事件（P1 过程事件地基）单测。

覆盖批次档 §2 验收对照：
1. 白名单字段改动 → 事件四要素齐全（who/when/old→new/source）
2. 审批路径 old 取提案快照
3. 非白名单字段（is_special/remark/sequence/assignees）零事件
4. 查询端点未登录 401、登录可查、过滤维度生效
5. 删用户后事件行保留（changed_by SET NULL + changed_by_name 冗余可读）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DataChangeEvent, Project, User
from app.services.change_events import (
    FIELD_LABELS,
    PHASE_PROPOSAL_FIELD_MAP,
    record_change_event,
)


# ---------- fixtures ----------

@pytest.fixture
def project(db_session: Session) -> Project:
    from app.services.project_code import next_project_code
    admin = db_session.query(User).filter_by(username="testadmin").first()
    p = Project(
        code=next_project_code(db_session),
        category="整机",
        name="过程事件测试项目",
        owner="客户A",
        market="亚太",
        status="进行中",
        priority="中",
        managed_by=admin.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def admin_user(db_session: Session) -> User:
    return db_session.query(User).filter_by(username="testadmin").first()


def _phase(db_session: Session, project: Project, **kw):
    from app.models import Phase
    defaults = dict(
        project_id=project.id, phase_type="P1", name="配置评估",
        sequence=1, status="未开始", progress=0, rework_count=0,
    )
    defaults.update(kw)
    ph = Phase(**defaults)
    db_session.add(ph)
    db_session.commit()
    db_session.refresh(ph)
    return ph


# ---------- 服务层 ----------

def test_record_change_event_basic(db_session: Session, admin_user: User, project: Project):
    record_change_event(
        db_session, user=admin_user, field="status", old="进行中", new="搁置",
        source="direct_edit", project_id=project.id, project_name=project.name,
    )
    db_session.commit()
    rows = db_session.query(DataChangeEvent).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.field == "status"
    assert r.old_value == "进行中"
    assert r.new_value == "搁置"
    assert r.source == "direct_edit"
    assert r.changed_by_name == admin_user.name
    assert r.project_name == "过程事件测试项目"
    assert FIELD_LABELS["status"] == "项目状态"


def test_record_rejects_non_whitelist(db_session: Session, admin_user: User):
    """非白名单字段直接 ValueError（写入侧拒绝，不给绕过）。"""
    with pytest.raises(ValueError, match="非白名单"):
        record_change_event(
            db_session, user=admin_user, field="remark", old="a", new="b", source="direct_edit",
        )
    with pytest.raises(ValueError, match="非法 source"):
        record_change_event(
            db_session, user=admin_user, field="status", old="a", new="b", source="excel_import",
        )


def test_date_serialized_isoformat(db_session: Session, admin_user: User, project: Project):
    from datetime import date
    record_change_event(
        db_session, user=admin_user, field="plan_start",
        old=date(2026, 1, 1), new=None, source="approval",
        project_id=project.id,
    )
    db_session.commit()
    r = db_session.query(DataChangeEvent).one()
    assert r.old_value == "2026-01-01"
    assert r.new_value is None


# ---------- 路由：update_project / update_phase ----------

def test_update_project_records_events(
    db_session: Session, client: TestClient, project: Project, admin_user: User,
):
    resp = client.put(f"/api/projects/{project.id}", json={
        "status": "搁置", "priority": "高", "remark": "备注不算过程字段",
    })
    assert resp.status_code == 200, resp.text
    rows = db_session.query(DataChangeEvent).order_by(DataChangeEvent.id).all()
    fields = [r.field for r in rows]
    # 白名单两条 + 非白名单零条
    assert "status" in fields and "priority" in fields
    assert "remark" not in fields and "is_special" not in fields
    by_field = {r.field: r for r in rows}
    assert by_field["status"].old_value == "进行中"
    assert by_field["status"].new_value == "搁置"
    assert by_field["status"].source == "direct_edit"


def test_update_phase_records_events(
    db_session: Session, client: TestClient, project: Project,
):
    ph = _phase(db_session, project, plan_start=None, plan_end=None)
    resp = client.put(f"/api/phases/{ph.id}", json={
        "status": "进行中", "progress": 40, "sequence": 2,
    })
    assert resp.status_code == 200, resp.text
    rows = db_session.query(DataChangeEvent).order_by(DataChangeEvent.id).all()
    fields = [r.field for r in rows]
    assert "phase_status" in fields and "progress" in fields
    assert rows[0].source == "direct_edit"
    # sequence 不在白名单
    assert "sequence" not in fields


def test_unchanged_fields_produce_zero_events(db_session, client, project, admin_user):
    """回归锁（#101 修复）：未改白名单字段零事件——旧 bug 会为每个未改字段产生伪事件。"""
    # 先记一笔，拿 before 快照（code/name/owner 等字段有值）
    resp = client.put(f"/api/projects/{project.id}", json={"status": "搁置"})
    assert resp.status_code == 200, resp.text
    rows = db_session.query(DataChangeEvent).all()
    fields = [r.field for r in rows]
    # 只应有 status 一条，不能有 code/name/owner/market/plan_start/plan_end/managed_by 等未改字段的伪事件
    assert fields == ["status"], f"预期仅 status 一条，实际: {fields}"


def test_date_resubmit_same_value_zero_events(db_session, client, project, admin_user):
    """回归锁（#101 修复）：date 对象 vs 字符串重提同值零事件。"""
    # 先设一个计划日期
    resp = client.put(f"/api/projects/{project.id}", json={"plan_start": "2026-02-01"})
    assert resp.status_code == 200, resp.text
    n1 = db_session.query(DataChangeEvent).count()
    # 用相同值再提一次（before 是 date 对象，after 是字符串）
    resp = client.put(f"/api/projects/{project.id}", json={"plan_start": "2026-02-01"})
    assert resp.status_code == 200, resp.text
    n2 = db_session.query(DataChangeEvent).count()
    assert n2 == n1, f"同值重提不应新增事件，{n1} → {n2}"


def test_rework_records_events(db_session: Session, client: TestClient, project: Project):
    ph = _phase(db_session, project, status="已完成", progress=100, rework_count=1)
    resp = client.post(f"/api/phases/{ph.id}/rework", json={
        "to_status": "未开始", "reason": "质量不达标",
    })
    assert resp.status_code == 200, resp.text
    rows = db_session.query(DataChangeEvent).order_by(DataChangeEvent.id).all()
    fields = [r.field for r in rows]
    assert fields == ["phase_status", "actual_end", "progress", "rework_count"]
    by_field = {r.field: r for r in rows}
    assert by_field["phase_status"].old_value == "已完成"
    assert by_field["phase_status"].new_value == "未开始"
    assert by_field["actual_end"].new_value is None
    assert by_field["progress"].new_value == "0"  # 序列化 TEXT 存储
    assert by_field["rework_count"].old_value == "1"
    assert by_field["rework_count"].new_value == "2"
    assert all(r.source == "rework" for r in rows)
    assert all(r.reason == "质量不达标" for r in rows)


# ---------- 查询端点 ----------

def test_events_endpoint_requires_auth():
    """未登录 401——用不覆盖依赖的原生 TestClient。"""
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/data-change-events").status_code == 401


def test_events_endpoint_filters(
    db_session: Session, client: TestClient, project: Project, admin_user: User,
):
    record_change_event(db_session, user=admin_user, field="status", old="a", new="b",
                        source="rework", project_id=project.id)
    record_change_event(db_session, user=admin_user, field="priority", old="c", new="d",
                        source="approval", project_id=project.id)
    db_session.commit()

    all_rows = client.get("/api/data-change-events").json()
    assert len(all_rows) >= 2
    assert {"field_label" in r for r in all_rows} == {True}

    by_source = client.get("/api/data-change-events", params={"source": "approval"}).json()
    assert {r["source"] for r in by_source} == {"approval"}
    by_field = client.get("/api/data-change-events", params={"field": "status"}).json()
    assert {r["field"] for r in by_field} == {"status"}
    by_proj = client.get("/api/data-change-events", params={"project_id": project.id}).json()
    assert {r["project_id"] for r in by_proj} == {project.id}


# ---------- 追溯：删用户后事件行保留 ----------

def test_event_survives_user_delete(db_session: Session, admin_user: User, project: Project):
    from datetime import datetime
    victim = User(
        username=f"victim_{datetime.now().timestamp():.0f}", name="删我", role="engineer",
        password_hash="x",
    )
    db_session.add(victim)
    db_session.commit()
    db_session.refresh(victim)
    record_change_event(
        db_session, user=victim, field="status", old="a", new="b",
        source="direct_edit", project_id=project.id,
    )
    db_session.commit()
    # 墓碑式删除（现有逻辑）
    victim.name = f"{victim.name}（已注销）"
    victim.is_active = False
    victim.force_deleted_at = datetime.now()
    db_session.commit()
    row = db_session.query(DataChangeEvent).one()
    assert row.changed_by_name == "删我"  # 冗余名保留


def test_proposal_field_map_only_whitelist():
    """审批提案映射只含白名单字段（name/sequence/assignee_ids 不入）。"""
    assert set(PHASE_PROPOSAL_FIELD_MAP) == {"plan_start", "plan_end", "phase_type"}
