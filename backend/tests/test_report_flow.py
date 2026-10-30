"""信息填报一期：业务流单测（新建/列表/审批流转/作废/单 pending）——随批次存档。

覆盖设计 §八：RT-1（新建落库/编号递增/sequence）、RT-3（审批流转）、RT-4（作废）
对应的后端面；字段级权限面在 test_report_auth.py。
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    OperationLog,
    Phase,
    PhaseChangeRequest,
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


def _mk_reporter_with_resource(db: Session, username: str, name: str) -> tuple[User, Resource]:
    res = Resource(name=name)
    db.add(res)
    db.flush()
    u = _mk_user(db, username, "reporter", name, resource_id=res.id)
    return u, res


# ---------- RT-1：新建项目 ----------

def test_create_project_reporter_defaults(client: TestClient, db_session: Session):
    """reporter 新建：编号自动递增、managed_by 默认自己、行序即 sequence、阶段名自动取类型名。"""
    _mk_reporter_with_resource(db_session, "rep_create", "填报人甲")
    db_session.commit()
    _login(client, "rep_create")
    meta = client.get("/api/report/meta").json()
    code_preview = meta["next_code"]

    resp = client.post("/api/report/projects", json={
        "category": "新需求",
        "name": "填报新建项目",
        "market": "拉美区",
        "status": "未开始",
        "phases": [
            {"phase_type": "P1", "plan_start": "2026-11-01", "plan_end": "2026-11-10", "assignee_ids": []},
            {"phase_type": "P4", "plan_start": "2026-11-11", "plan_end": "2026-11-30", "assignee_ids": []},
        ],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == code_preview  # 纯数字递增（首个项目=1）
    assert body["is_mine"] is True
    assert body["managed_by_name"] == "填报人甲"
    seqs = [p["sequence"] for p in body["phases"]]
    assert seqs == [1, 2]
    assert body["phases"][0]["name"] == "需求评估"
    assert body["phases"][1]["name"] == "工业设计"
    # 列表出现新项目
    ids = [p["id"] for p in client.get("/api/report/projects").json()]
    assert body["id"] in ids


def test_create_project_invalid_category_and_dates(client: TestClient, db_session: Session):
    """类目非法 400；行级校验：结束<开始 400；工程/观察角色 403。"""
    _mk_reporter_with_resource(db_session, "rep_create2", "填报人乙")
    _mk_user(db_session, "eng_rep", "engineer", "工程师甲")
    db_session.commit()
    _login(client, "rep_create2")
    resp = client.post("/api/report/projects", json={
        "category": "定制", "name": "X", "market": "拉美区"})
    assert resp.status_code == 400
    resp = client.post("/api/report/projects", json={
        "category": "新需求", "name": "X", "market": "拉美区",
        "phases": [{"phase_type": "P1", "plan_start": "2026-11-10", "plan_end": "2026-11-01"}]})
    assert resp.status_code == 400
    assert "结束" in resp.json()["detail"]
    _login(client, "eng_rep")
    resp = client.post("/api/report/projects", json={
        "category": "新需求", "name": "X", "market": "拉美区"})
    assert resp.status_code == 403


def test_create_project_invalid_phase_type_and_managed_by_type(client: TestClient, db_session: Session):
    """评审修复回归：phase_type 非法 400（§九-3 仅平台 10 类）；managed_by 类型非法 400（裸 dict 500 修复）。"""
    u, _r = _mk_reporter_with_resource(db_session, "rep_create3", "填报人丙")
    p = Project(code="9004", category="新需求", name="校验项目", owner="填报人丙",
                market="拉美区", status="未开始", managed_by=u.id)
    db_session.add(p)
    db_session.commit()
    _login(client, "rep_create3")
    resp = client.post("/api/report/projects", json={
        "category": "新需求", "name": "X", "market": "拉美区",
        "phases": [{"phase_type": "自定义X"}]})
    assert resp.status_code == 400
    assert "10 类" in resp.json()["detail"]
    # managed_by 错误类型：400 而非 500（需本人为负责人的项目，先过 403/404 才到类型校验）
    resp = client.patch(f"/api/report/projects/{p.id}", json={"managed_by": "abc"})
    assert resp.status_code == 400
    assert "类型非法" in resp.json()["detail"]


def test_project_progress_mean(client: TestClient, db_session: Session):
    """项目进度 = 名下阶段 progress 均值；无阶段 → null（前端显示"—"）。"""
    u, _r = _mk_reporter_with_resource(db_session, "rep_prog", "进度人")
    p = Project(code="9002", category="新需求", name="进度项目", owner="进度人",
                market="亚太区", status="进行中", managed_by=u.id)
    db_session.add(p)
    db_session.flush()
    db_session.add(Phase(project_id=p.id, phase_type="P1", name="需求评估", sequence=1,
                         status="进行中", progress=30))
    db_session.add(Phase(project_id=p.id, phase_type="P4", name="工业设计", sequence=2,
                         status="进行中", progress=90))
    db_session.commit()
    _login(client, "rep_prog")
    items = client.get("/api/report/projects").json()
    row = next(i for i in items if i["id"] == p.id)
    assert row["progress"] == 60
    # 无阶段项目
    p2 = Project(code="9003", category="新需求", name="空项目", owner="进度人",
                 market="亚太区", status="未开始", managed_by=u.id)
    db_session.add(p2)
    db_session.commit()
    items = client.get("/api/report/projects").json()
    row2 = next(i for i in items if i["id"] == p2.id)
    assert row2["progress"] is None


# ---------- RT-3：改期审批流转 ----------

def _setup_change_flow(db_session: Session):
    """负责人 + 阶段负责人（含资源）+ 项目/阶段。"""
    owner = _mk_user(db_session, "flow_owner", "reporter", "审批负责人")
    assignee_u, assignee_res = _mk_reporter_with_resource(db_session, "flow_assignee", "申请阶段员")
    project = Project(code="9004", category="新需求", name="审批流项目", owner="审批负责人",
                      market="拉美区", status="进行中", managed_by=owner.id)
    db_session.add(project)
    db_session.flush()
    phase = Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1,
                  plan_start=date(2026, 11, 1), plan_end=date(2026, 11, 10),
                  status="进行中", progress=20)
    db_session.add(phase)
    db_session.flush()
    db_session.execute(phase_assignee.insert().values(phase_id=phase.id,
                                                      resource_id=assignee_res.id))
    db_session.commit()
    return owner, assignee_u, project, phase


def test_change_request_full_flow(client: TestClient, db_session: Session):
    """提交 → 待审列表 → 批准：Phase 更新 + operation_log；驳回路径：Phase 原值不动。"""
    _o, assignee_u, project, phase = _setup_change_flow(db_session)
    _login(client, "flow_assignee")
    # 提交（old 由服务端捕获）
    resp = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-11-05", "plan_end": "2026-11-15"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["proposed"]["plan_start"] == {"old": "2026-11-01", "new": "2026-11-05"}
    assert body["proposed"]["plan_end"] == {"old": "2026-11-10", "new": "2026-11-15"}
    req_id = body["id"]

    # 负责人待审列表可见
    _login(client, "flow_owner")
    pending = client.get("/api/report/change-requests").json()
    assert any(r["id"] == req_id for r in pending)
    # 批准
    resp = client.post(f"/api/report/change-requests/{req_id}/review",
                       json={"approved": True})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    ph = db_session.get(Phase, phase.id)
    assert str(ph.plan_start) == "2026-11-05"
    assert str(ph.plan_end) == "2026-11-15"
    # operation_log 一条（approve_report_phase_change）
    logs = db_session.query(OperationLog).filter(
        OperationLog.action == "approve_report_phase_change").all()
    assert len(logs) == 1

    # 驳回路径：Phase 原值不动 + 原因必填（第二笔须语义合法——两字段一起挪，倒挂已被新校验拦）
    _login(client, "flow_assignee")
    resp = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-12-01", "plan_end": "2026-12-15"})
    assert resp.status_code == 201
    # 倒挂区间防护：仅挪 start 而落在现值 end（11-10）之后 → 400（提交门合并校验；
    # 前一笔 pending 在位时仍先报单 pending，故倒挂断言放在 pending 断言之后独立提交）
    bad = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2027-01-01"})
    assert bad.status_code == 400
    assert "待审批" in bad.json()["detail"]
    req_id2 = resp.json()["id"]
    _login(client, "flow_owner")
    assert client.post(f"/api/report/change-requests/{req_id2}/review",
                       json={"approved": False}).status_code == 400  # 缺原因
    resp = client.post(f"/api/report/change-requests/{req_id2}/review",
                       json={"approved": False, "comment": "周期不合理"})
    assert resp.status_code == 200
    db_session.expire_all()
    ph = db_session.get(Phase, phase.id)
    assert str(ph.plan_start) == "2026-11-05"  # 驳回不改


def test_single_pending_enforced(client: TestClient, db_session: Session):
    """同阶段已有 pending → 再次提交 400（§四边界规则 1）。"""
    _o, assignee_u, project, phase = _setup_change_flow(db_session)
    _login(client, "flow_assignee")
    r1 = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-11-05"})
    assert r1.status_code == 201
    r2 = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_end": "2026-11-20"})
    assert r2.status_code == 400
    assert "待审批" in r2.json()["detail"]


def test_only_assignee_can_request_owner_direct(client: TestClient, db_session: Session):
    """非阶段负责人提交 403；负责人提交被引导直改 400。"""
    _o, _a, project, phase = _setup_change_flow(db_session)
    _mk_reporter_with_resource(db_session, "flow_other", "无关人")
    db_session.commit()
    _login(client, "flow_other")
    assert client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-11-05"}).status_code == 403
    _login(client, "flow_owner")
    resp = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-11-05"})
    assert resp.status_code == 400
    assert "直接修改" in resp.json()["detail"]


def test_review_permission_owner_only(client: TestClient, db_session: Session):
    """审批仅项目负责人；他人/申请人 403；重复审批 400。"""
    _o, assignee_u, project, phase = _setup_change_flow(db_session)
    _mk_reporter_with_resource(db_session, "flow_other2", "无关人二")
    db_session.commit()
    _login(client, "flow_assignee")
    req_id = client.post("/api/report/change-requests", json={
        "phase_id": phase.id, "plan_start": "2026-11-05"}).json()["id"]
    _login(client, "flow_other2")
    assert client.post(f"/api/report/change-requests/{req_id}/review",
                       json={"approved": True}).status_code == 403
    _login(client, "flow_assignee")
    assert client.post(f"/api/report/change-requests/{req_id}/review",
                       json={"approved": True}).status_code == 403
    _login(client, "flow_owner")
    assert client.post(f"/api/report/change-requests/{req_id}/review",
                       json={"approved": True}).status_code == 200
    # 已批准后再批 → 400
    assert client.post(f"/api/report/change-requests/{req_id}/review",
                       json={"approved": True}).status_code == 400


# ---------- 项目级字段（负责人） ----------

def test_project_patch_owner_only(client: TestClient, db_session: Session):
    """项目级字段：负责人可改；非负责人整请求 403 附字段名；非法字段 400。"""
    owner, _a, project, phase = _setup_change_flow(db_session)
    _login(client, "flow_assignee")
    resp = client.patch(f"/api/report/projects/{project.id}", json={"name": "偷改名"})
    assert resp.status_code == 403
    assert "name" in resp.json()["detail"]
    _login(client, "flow_owner")
    resp = client.patch(f"/api/report/projects/{project.id}",
                        json={"name": "改名了", "status": "已完成"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名了"
    assert resp.json()["status"] == "已完成"
    # 非法字段
    resp = client.patch(f"/api/report/projects/{project.id}", json={"code": "9999"})
    assert resp.status_code == 400


def test_meta_endpoint(client: TestClient, db_session: Session):
    """meta：枚举齐全 + 编号预览 + 选人下拉。"""
    _mk_reporter_with_resource(db_session, "rep_meta", "元数据人")
    db_session.commit()
    _login(client, "rep_meta")
    meta = client.get("/api/report/meta").json()
    assert meta["categories"] == ["新需求", "量产升级", "改造"]
    assert len(meta["markets"]) == 10
    assert len(meta["phase_types"]) == 10
    assert meta["project_statuses"] == ["未开始", "进行中", "已完成", "搁置"]
    assert meta["phase_statuses"] == ["未开始", "进行中", "已完成", "延期", "搁置"]
    assert isinstance(meta["next_code"], str)
    assert any(u["role"] == "reporter" for u in meta["users"])
