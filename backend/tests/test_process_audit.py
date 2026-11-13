"""P3 过程事件审计分析单测（批档 P3过程事件审计分析-2026-11-12 §2 四、测试面；RT-13 对应单测面）。

覆盖（判据→断言映射）：
1. 计划稳定性口径：次数（按字段变更事件计）/挪动天数 Σ|new−old|（分列+合计）/解析失败显式计数
2. 估算偏差三分支：有事件（最早事件 old_value 为首次值）/无事件（phase 现值即首次）/成对缺失 → first_plan_skipped
3. 审批时效：已决（approved/rejected）均值、pending 不计、仅 approved 均值可切换
4. 窗口过滤（created_at/actual_end/reviewed_at ∈ 窗口）+ 市场过滤（Project.market）+ 单项目过滤
5. 防火墙：返回体无按人（changed_by）维度；守卫：401 未登录拒、reporter 403（封锁矩阵）
"""
from __future__ import annotations

import itertools
from datetime import date, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import DataChangeEvent, Phase, PhaseChangeRequest, Project, User

_CODE_SEQ = itertools.count(1)


# ---------- fixtures / helpers ----------

def _d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


def _dt(days_ago: int, hour: int = 12) -> datetime:
    return datetime.combine(_d(days_ago), time(hour, 0))


def _mk_project(db: Session, name: str, market: str = "拉美区") -> Project:
    p = Project(code=f"PA{next(_CODE_SEQ)}", category="新需求", name=name, owner="张三",
                market=market, status="进行中")
    db.add(p)
    db.flush()
    return p


def _mk_phase(db: Session, project: Project, name: str = "阶段甲", sequence: int = 1,
              plan_start: date | None = None, plan_end: date | None = None,
              actual_start: date | None = None, actual_end: date | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P1", name=name, sequence=sequence,
               plan_start=plan_start, plan_end=plan_end,
               actual_start=actual_start, actual_end=actual_end,
               status="已完成" if actual_end else "未开始", progress=0, rework_count=0)
    db.add(ph)
    db.flush()
    return ph


def _ev(db: Session, field: str, old: str | None, new: str | None, *,
        created_at: datetime, project: Project | None = None, phase: Phase | None = None,
        project_name: str | None = None) -> DataChangeEvent:
    """直插事件行（created_at 显式可控——窗口过滤判定用）。"""
    row = DataChangeEvent(
        project_id=project.id if project else None,
        phase_id=phase.id if phase else None,
        field=field, old_value=old, new_value=new, source="direct_edit",
        changed_by=None, changed_by_name="张三",  # 按人身份字段——防火墙断言不得外泄
        project_name=project_name or (project.name if project else None),
        phase_name=phase.name if phase else None,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _req(db: Session, project: Project, phase: Phase, *, status: str,
         created_at: datetime, reviewed_at: datetime | None) -> PhaseChangeRequest:
    admin = db.query(User).filter_by(username="testadmin").first()
    row = PhaseChangeRequest(phase_id=phase.id, project_id=project.id,
                             requested_by=admin.id, status=status,
                             created_at=created_at, reviewed_at=reviewed_at)
    db.add(row)
    db.flush()
    return row


def _get(client: TestClient, days: int = 30, market: str | None = None,
         project_id: int | None = None) -> dict:
    params: dict = {"days": days}
    if market is not None:
        params["market"] = market
    if project_id is not None:
        params["project_id"] = project_id
    resp = client.get("/api/analysis/process-audit", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stab_row(data: dict, project_id: int | None) -> dict:
    rows = [r for r in data["plan_stability"] if r["project_id"] == project_id]
    assert len(rows) == 1, f"预期 1 行（project_id={project_id}），实际 {data['plan_stability']}"
    return rows[0]


# ---------- 1. 计划稳定性口径 ----------

def test_plan_stability_counts_and_move_days(client: TestClient, db_session: Session):
    """次数按字段变更事件计（一次编辑同改两字段 = 2 次）；挪动 Σ|new−old| 分列+合计。"""
    p = _mk_project(db_session, "稳定性项目")
    ph = _mk_phase(db_session, p)
    _ev(db_session, "plan_start", "2026-10-01", "2026-10-06", created_at=_dt(20), project=p)  # 5 天
    _ev(db_session, "plan_end", "2026-10-10", "2026-10-20", created_at=_dt(15), project=p)  # 10 天
    _ev(db_session, "phase_plan_start", "2026-10-01", "2026-10-03", created_at=_dt(10), project=p, phase=ph)  # 2 天
    _ev(db_session, "phase_plan_end", "2026-10-05", "2026-10-02", created_at=_dt(5), project=p, phase=ph)  # 3 天（绝对值）
    db_session.commit()

    data = _get(client, days=30)
    assert data["days"] == 30
    row = _stab_row(data, p.id)
    assert row["change_count_project"] == 2
    assert row["change_count_phase"] == 2
    assert row["move_days_project"] == 15
    assert row["move_days_phase"] == 5
    assert row["move_days_total"] == 20
    assert data["move_parse_skipped"] == 0


def test_plan_stability_parse_failure_counted_not_dropped(client: TestClient, db_session: Session):
    """解析失败（空 old_value/非日期字面）显式计数：次数照计、天数不计、不静默丢弃。"""
    p = _mk_project(db_session, "解析失败项目")
    _ev(db_session, "plan_start", None, "2026-10-05", created_at=_dt(5), project=p)  # 日期首次设置无旧值
    _ev(db_session, "plan_end", "2026-10-01", "not-a-date", created_at=_dt(5), project=p)
    db_session.commit()

    data = _get(client, days=30)
    row = _stab_row(data, p.id)
    assert row["change_count_project"] == 2  # 不静默丢弃
    assert row["move_days_project"] == 0  # 不计天数
    assert data["move_parse_skipped"] == 2  # 显式计数


# ---------- 2. 估算偏差三分支 ----------

def test_estimation_three_branches(client: TestClient, db_session: Session):
    """有事件（最早事件 old_value 为首次值）/无事件（phase 现值即首次）/成对缺失 → first_plan_skipped。"""
    p = _mk_project(db_session, "估算项目")

    # 分支①有事件：首值取最早事件 old_value（事件史回溯不受窗口限制——created_at 放窗口外）
    ph_a = _mk_phase(db_session, p, "有事件阶段", sequence=1,
                     plan_start=_d(25), plan_end=_d(8),
                     actual_start=_d(12), actual_end=_d(5))
    _ev(db_session, "phase_plan_start", _d(30).isoformat(), _d(25).isoformat(),
        created_at=_dt(200), project=p, phase=ph_a)
    _ev(db_session, "phase_plan_start", _d(25).isoformat(), _d(22).isoformat(),
        created_at=_dt(150), project=p, phase=ph_a)  # 后续事件——首值仍取最早事件 old_value
    _ev(db_session, "phase_plan_end", _d(10).isoformat(), _d(8).isoformat(),
        created_at=_dt(200), project=p, phase=ph_a)

    # 分支②无事件：首值 = phase 对应列现值（未改过即首次）
    _mk_phase(db_session, p, "无事件阶段", sequence=2,
              plan_start=_d(20), plan_end=_d(12),
              actual_start=_d(15), actual_end=_d(4))

    # 分支③成对缺失：phase_plan_end 首次设置（old_value 空）→ 首值缺失，列现值不救
    ph_c = _mk_phase(db_session, p, "成对缺失阶段", sequence=3,
                     plan_start=_d(15), plan_end=_d(3),
                     actual_start=_d(2), actual_end=_d(3))
    _ev(db_session, "phase_plan_end", None, _d(3).isoformat(),
        created_at=_dt(60), project=p, phase=ph_c)
    db_session.commit()

    data = _get(client, days=30)
    rows = {r["phase_name"]: r for r in data["estimation_deviation"]}
    assert set(rows) == {"有事件阶段", "无事件阶段"}
    assert data["first_plan_skipped"] == 1

    a = rows["有事件阶段"]
    assert a["first_plan_start"] == _d(30).isoformat()
    assert a["first_plan_end"] == _d(10).isoformat()
    assert a["plan_duration_days"] == 20
    assert a["actual_start"] == _d(12).isoformat()
    assert a["actual_end"] == _d(5).isoformat()
    assert a["actual_duration_days"] == 7
    assert a["deviation_days"] == -13
    assert a["delivery_deviation_days"] == 5

    b = rows["无事件阶段"]
    assert b["first_plan_start"] == _d(20).isoformat()
    assert b["first_plan_end"] == _d(12).isoformat()
    assert b["plan_duration_days"] == 8
    assert b["actual_duration_days"] == 11
    assert b["deviation_days"] == 3
    assert b["delivery_deviation_days"] == 8


# ---------- 3. 审批时效 ----------

def test_approval_latency_decided_mean_pending_excluded(client: TestClient, db_session: Session):
    """已决（approved/rejected）均值含驳回件；pending 不计；仅 approved 均值可切换。"""
    p = _mk_project(db_session, "审批项目")
    ph1 = _mk_phase(db_session, p, "阶段一")
    ph2 = _mk_phase(db_session, p, "阶段二", sequence=2)
    _req(db_session, p, ph1, status="approved", created_at=_dt(10, 8), reviewed_at=_dt(10, 18))  # 10h
    _req(db_session, p, ph1, status="rejected", created_at=_dt(9, 12), reviewed_at=_dt(8, 12))  # 24h
    _req(db_session, p, ph2, status="pending", created_at=_dt(30), reviewed_at=None)  # 不计
    db_session.commit()

    data = _get(client, days=30)
    lat = data["approval_latency"]
    assert lat["avg_hours"] == 17  # (10 + 24) / 2，含驳回件
    assert lat["count"] == 2
    assert lat["approved_avg_hours"] == 10  # 仅 approved 均值（切换口径）
    assert lat["approved_count"] == 1


# ---------- 4. 窗口/市场/单项目过滤 ----------

def test_window_filter_all_three_metrics(client: TestClient, db_session: Session):
    """窗口过滤：40 天前的事件/阶段完成/审批决于在 days=30 全部出窗、days=90 全部入窗。"""
    p = _mk_project(db_session, "窗口项目")
    _ev(db_session, "plan_start", _d(41).isoformat(), _d(40).isoformat(), created_at=_dt(40), project=p)
    _ev(db_session, "plan_start", _d(6).isoformat(), _d(5).isoformat(), created_at=_dt(5), project=p)
    _mk_phase(db_session, p, "窗口外阶段",
              plan_start=_d(60), plan_end=_d(50), actual_end=_d(40))
    _req(db_session, p, _mk_phase(db_session, p, "审批阶段", sequence=2),
         status="approved", created_at=_dt(41), reviewed_at=_dt(40))
    db_session.commit()

    data30 = _get(client, days=30)
    assert _stab_row(data30, p.id)["change_count_project"] == 1
    assert data30["estimation_deviation"] == []
    assert data30["first_plan_skipped"] == 0  # 窗外阶段不入候选，也不进 skipped
    assert data30["approval_latency"]["count"] == 0

    data90 = _get(client, days=90)
    assert _stab_row(data90, p.id)["change_count_project"] == 2
    assert [r["phase_name"] for r in data90["estimation_deviation"]] == ["窗口外阶段"]
    assert data90["approval_latency"]["count"] == 1


def test_market_and_project_filters(client: TestClient, db_session: Session):
    """市场过滤锚 Project.market；project_id 过滤单项目明细——三指标同源生效。"""
    pa = _mk_project(db_session, "拉美项目", market="拉美区")
    pb = _mk_project(db_session, "西欧项目", market="西欧区")
    for proj in (pa, pb):
        _ev(db_session, "plan_start", _d(2).isoformat(), _d(1).isoformat(), created_at=_dt(3), project=proj)
        _mk_phase(db_session, proj, "阶段甲",
                  plan_start=_d(30), plan_end=_d(20), actual_start=_d(15), actual_end=_d(5))
        _req(db_session, proj, _mk_phase(db_session, proj, "阶段乙", sequence=2),
             status="approved", created_at=_dt(3, 12), reviewed_at=_dt(2, 12))
    db_session.commit()

    latam = _get(client, days=30, market="拉美区")
    assert [r["project_id"] for r in latam["plan_stability"]] == [pa.id]
    assert [r["project_id"] for r in latam["estimation_deviation"]] == [pa.id]
    assert latam["approval_latency"]["count"] == 1

    only_b = _get(client, days=30, project_id=pb.id)
    assert [r["project_id"] for r in only_b["plan_stability"]] == [pb.id]
    assert [r["project_id"] for r in only_b["estimation_deviation"]] == [pb.id]
    assert only_b["approval_latency"]["count"] == 1


def test_data_start_global_and_deleted_project_row_kept(client: TestClient, db_session: Session):
    """data_start 取全库首事件日（不受窗口过滤）；已删项目事件按冗余名归行保留（不静默丢弃）。"""
    p = _mk_project(db_session, "起点项目")
    _ev(db_session, "plan_start", _d(201).isoformat(), _d(200).isoformat(), created_at=_dt(200), project=p)
    _ev(db_session, "plan_start", "2026-10-01", "2026-10-02",
        created_at=_dt(5), project=None, project_name="幽灵项目")
    db_session.commit()

    data = _get(client, days=30)
    assert data["data_start"] == _d(200).isoformat()  # 窗口外首事件仍报数据起点
    ghost = _stab_row(data, None)
    assert ghost["project_name"] == "幽灵项目"
    assert ghost["change_count_project"] == 1


# ---------- 5. 防火墙 + 守卫 ----------

def test_firewall_no_person_dimension(client: TestClient, db_session: Session):
    """防火墙：返回体无按人（changed_by）维度——键集锁死为契约字段，按人身份字段不得外泄。"""
    p = _mk_project(db_session, "防火墙项目")
    _ev(db_session, "plan_start", "2026-10-01", "2026-10-02", created_at=_dt(5), project=p)
    ph = _mk_phase(db_session, p, "阶段甲", plan_start=_d(20), plan_end=_d(10),
                   actual_start=_d(8), actual_end=_d(4))
    _req(db_session, p, ph, status="approved", created_at=_dt(3, 8), reviewed_at=_dt(3, 12))
    db_session.commit()

    resp = client.get("/api/analysis/process-audit", params={"days": 365})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"days", "data_start", "plan_stability", "estimation_deviation",
                         "approval_latency", "move_parse_skipped", "first_plan_skipped"}
    for row in data["plan_stability"]:
        assert set(row) == {"project_id", "project_name", "change_count_project",
                            "change_count_phase", "move_days_project", "move_days_phase",
                            "move_days_total"}
    for row in data["estimation_deviation"]:
        assert set(row) == {"project_id", "project_name", "phase_id", "phase_name",
                            "first_plan_start", "first_plan_end", "actual_start", "actual_end",
                            "plan_duration_days", "actual_duration_days", "deviation_days",
                            "delivery_deviation_days"}
    assert set(data["approval_latency"]) == {"avg_hours", "count",
                                             "approved_avg_hours", "approved_count"}
    # 按人身份字段/人名不得出现在返回体（不做绩效评分/排名）
    for token in ("changed_by", "requested_by", "reviewed_by", "张三"):
        assert token not in resp.text, f"返回体泄漏按人维度：{token}"


def test_endpoint_requires_auth():
    """未登录 401——用不覆盖依赖的原生 TestClient。"""
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/analysis/process-audit").status_code == 401


def test_reporter_blocked_by_lockdown(client: TestClient, db_session: Session):
    """reporter 403（封锁矩阵：/api/analysis 非放行面）。"""
    rep = User(username="rep_pa", name="填报人甲", role="reporter",
               password_hash=hash_password("testpass"), must_change_password=False)
    db_session.add(rep)
    db_session.commit()
    resp = client.post("/api/auth/login", json={"username": "rep_pa", "password": "testpass"})
    assert resp.status_code == 200, resp.text
    assert client.get("/api/analysis/process-audit", params={"days": 30}).status_code == 403


def test_days_invalid_400(client: TestClient):
    """days 仅 30/90/365 三档（§4.6 批复口径）。"""
    assert client.get("/api/analysis/process-audit", params={"days": 180}).status_code == 400
