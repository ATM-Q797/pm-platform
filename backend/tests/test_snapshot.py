"""每日状态快照测试（PROJECT_ANALYSIS §四 4/5）。

覆盖：
- snapshots/run 幂等（首次 201 建行 / 同日 200 skipped / 当日恰 1 行）
- 专项项目不计入任何指标（用户裁定 1，硬约束）
- 搁置项目的逾期阶段不计入延期
- trend 周聚合（周一锚点）与累计量差分正确
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from app.models import Phase, Project, Resource, StatusSnapshot
from app.services.snapshot import build_trend, create_today_if_absent


def _mk_project(db, name: str, *, is_special: bool = False, status: str = "进行中") -> Project:
    p = Project(code=str(len(list(db.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区", status=status,
                is_special=is_special)
    db.add(p)
    db.flush()
    return p


def _mk_phase(db, project: Project, name: str, start: date, end: date,
              status: str = "进行中", phase_type: str = "P4") -> Phase:
    ph = Phase(project_id=project.id, phase_type=phase_type, name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50)
    db.add(ph)
    db.flush()
    return ph


# ---------- 幂等 ----------

def test_snapshot_run_idempotent(client, db_session):
    """run：首次 201 建行、同日再调 200 skipped，当日恰 1 行。"""
    t = date.today()
    p = _mk_project(db_session, "快照项目")
    _mk_phase(db_session, p, "正常阶段", t, t + timedelta(days=10))
    db_session.commit()

    r1 = client.post("/api/analysis/snapshots/run")
    assert r1.status_code == 201
    body1 = r1.json()
    assert body1["created"] is True
    assert body1["snapshot_date"] == t.isoformat()
    assert body1["metrics"]["projects_total"] == 1

    r2 = client.post("/api/analysis/snapshots/run")
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["metrics"] == body1["metrics"]

    assert db_session.scalar(select(func.count()).select_from(StatusSnapshot)) == 1
    assert db_session.scalar(
        select(func.count()).select_from(StatusSnapshot)
        .where(StatusSnapshot.snapshot_date == t)
    ) == 1


def test_create_today_if_absent_service_level(db_session):
    """服务层幂等：两次调用一次建行一次跳过，同一行；metrics 为采集结果。"""
    snap1, created1 = create_today_if_absent(db_session)
    assert created1 is True
    snap2, created2 = create_today_if_absent(db_session)
    assert created2 is False
    assert snap2.id == snap1.id
    assert isinstance(snap1.metrics, dict)
    assert "projects_total" in snap1.metrics
    assert "conflict_pairs" in snap1.metrics


# ---------- 专项排除（裁定 1）+ 搁置延期排除 + 口径 ----------

def test_snapshot_excludes_special_and_shelved(client, db_session):
    """专项项目不计入任何指标；搁置项目延期不计入；p50/p90/热力指标正确。

    数据全景（today=t）：
    - normal1 进行中：正常阶段(t-2,t+12 进行中)、已完成阶段(已完成)
    - normal2 进行中：逾期甲(end=t-15, 逾期15天)、逾期乙(end=t-25, 逾期25天)
    - shelved 搁置：搁置逾期阶段(end=t-5, 项目搁置 → 延期不计入)
    - special_delayed 专项：专项逾期阶段(end=t-20)、专项已完成阶段(已完成)——全排除
    - special_shelved 专项+搁置：专项搁置阶段(t,t+3 将到期)——全排除
    - 冲突构造：王五 = 专项逾期阶段 + B/F1/F2(三个常规项目,深重叠)——
      专项若不排除会成冲突对；排除后剩余 3 阶段并行=3 ≤ 3 → conflict_pairs=0
    """
    t = date.today()

    normal1 = _mk_project(db_session, "常规项目一")
    _mk_phase(db_session, normal1, "正常阶段", t - timedelta(days=2), t + timedelta(days=12))
    _mk_phase(db_session, normal1, "已完成阶段", t - timedelta(days=9), t - timedelta(days=8), status="已完成")

    normal2 = _mk_project(db_session, "常规项目二")
    _mk_phase(db_session, normal2, "逾期甲", t - timedelta(days=20), t - timedelta(days=15))
    _mk_phase(db_session, normal2, "逾期乙", t - timedelta(days=30), t - timedelta(days=25))

    shelved = _mk_project(db_session, "搁置项目", status="搁置")
    _mk_phase(db_session, shelved, "搁置逾期阶段", t - timedelta(days=10), t - timedelta(days=5))

    special_delayed = _mk_project(db_session, "专项延期", is_special=True)
    sp_late = _mk_phase(db_session, special_delayed, "专项逾期阶段", t - timedelta(days=30), t - timedelta(days=20))
    _mk_phase(db_session, special_delayed, "专项已完成阶段", t - timedelta(days=10), t - timedelta(days=9), status="已完成")

    special_shelved = _mk_project(db_session, "专项搁置", is_special=True, status="搁置")
    _mk_phase(db_session, special_shelved, "专项搁置阶段", t, t + timedelta(days=3))

    # 冲突构造（深重叠 + 若专项不排除则并行=4 > 3 必报）
    wang = Resource(name="王五")
    db_session.add(wang)
    db_session.flush()
    b = _mk_phase(db_session, _mk_project(db_session, "冲突项目甲"), "冲突阶段B", t + timedelta(days=8), t + timedelta(days=38))
    f1 = _mk_phase(db_session, _mk_project(db_session, "冲突项目乙"), "冲突阶段F1", t, t + timedelta(days=28))
    f2 = _mk_phase(db_session, _mk_project(db_session, "冲突项目丙"), "冲突阶段F2", t, t + timedelta(days=30))
    for ph in (sp_late, b, f1, f2):
        ph.assignees = [wang]
    db_session.commit()

    r = client.post("/api/analysis/snapshots/run")
    assert r.status_code == 201
    m = r.json()["metrics"]

    # 项目计数：6 个常规（5 进行中 + 1 搁置）；专项 2 个不计入
    assert m["projects_total"] == 6
    assert m["projects_by_status"] == {"进行中": 5, "搁置": 1}
    assert m["shelved_total"] == 1

    # 延期：逾期甲/乙 计入；搁置项目与专项的逾期阶段不计入
    assert m["delayed_phases"] == 2
    assert m["delayed_projects"] == 1
    # 深度分位：sorted [15,25] → p50=20, p90=24（线性插值）
    assert m["delayed_days_p50"] == 20
    assert m["delayed_days_p90"] == 24

    # 即将到期：专项搁置阶段(t+3)不计入 → 0
    assert m["due_soon_phases"] == 0

    # 冲突：专项排除后 3 阶段并行 ≤ 3 → 0 对（专项若计入则必报）
    assert m["conflict_pairs"] == 0

    # 热力口径（专项阶段不占格）：王五峰值并行 = 3（B/F1/F2）
    assert m["active_people"] == 1
    assert m["peak_parallel_top3_avg"] == 3.0

    # 吞吐累计：已完成阶段仅常规 1 个（专项已完成不计入）
    assert m["completed_phases_total"] == 1
    # 未完成阶段（设计 §二字面：状态 ∉{已完成,搁置}，排除专项）：
    # 正常阶段/逾期甲/逾期乙/搁置逾期阶段/B/F1/F2 = 7
    assert m["open_phases"] == 7

    # ---- 项目级扩展（四板块，用户 2026-10-26）----
    # 在期 = 未开始+进行中 = 5
    assert m["in_flight_projects"] == 5
    # 7 天内到期项目：各项目均无项目级 plan_end（None）→ 0
    assert m["due_soon_projects"] == 0
    # 计划工期异常：本用例阶段级日期，项目级 plan_start/end 均空 → 0/0
    assert m["plan_days_too_long"] == 0
    assert m["plan_days_too_short"] == 0
    # 吞吐累计（项目级）：完成 0、已开工（plan_start<=today 且状态活跃/完成）0（均无项目级日期）
    assert m["completed_projects_total"] == 0
    assert m["started_projects_total"] == 0
    # 市场分布（非专项）：全部 _mk_project 默认拉美区 ×6
    assert m["projects_by_market"] == {"拉美区": 6}
    assert m["projects_by_category"] == {"新需求": 6}


# ---------- trend：周聚合 + 差分 ----------

def test_trend_weekly_aggregation_and_delta(client, db_session):
    """周点 = 周内最后一个快照；delta 仅累计量键、首周为 0；窗口按天过滤。

    日期构造与今天星期几无关：上周两个快照（早/晚）+ 今天一个；
    上周周点 = 晚者覆盖早者。
    """
    t = date.today()
    monday0 = t - timedelta(days=t.weekday())          # 本周一
    last_monday = monday0 - timedelta(days=7)          # 上周一

    # (日期, projects_total, completed_phases_total, shelved_total)
    plan = [
        (last_monday, 10, 100, 2),
        (last_monday + timedelta(days=5), 11, 104, 3),  # 上周六：覆盖周一 → 周点=11
        (t, 15, 120, 4),                                # 今天：本周唯一点
    ]
    for d, pt, pc, ps in plan:
        db_session.add(StatusSnapshot(
            snapshot_date=d,
            metrics={"projects_total": pt, "completed_phases_total": pc, "shelved_total": ps},
        ))
    db_session.commit()

    data = client.get("/api/analysis/trend?days=30").json()
    assert data["days"] == 30
    assert len(data["daily"]) == 3
    assert data["daily"][-1]["metrics"]["projects_total"] == 15

    weekly = data["weekly"]
    assert [w["week_start"] for w in weekly] == [last_monday.isoformat(), monday0.isoformat()]
    # 周点 = 周内最后一个快照
    assert weekly[0]["metrics"]["projects_total"] == 11
    assert weekly[1]["metrics"]["projects_total"] == 15
    # 差分：首周 0；本周 = 本周值 - 上周值（键集 = _WEEKLY_DELTA_KEYS，项目级，用户 2026-10-26 裁定）
    assert weekly[0]["delta"] == {"completed_projects_total": 0, "shelved_total": 0, "started_projects_total": 0}
    assert weekly[1]["delta"] == {"completed_projects_total": 0, "shelved_total": 1, "started_projects_total": 0}

    # 窗口下界（纯函数级）：days=3 → 仅窗口内快照（端点层 days 固定 30/90/180）
    row_old = StatusSnapshot(snapshot_date=date(2026, 9, 7), metrics={"projects_total": 1})
    row_in = StatusSnapshot(snapshot_date=date(2026, 9, 16), metrics={"projects_total": 2})
    out4 = build_trend([row_old, row_in], days=3, today=date(2026, 9, 18))
    assert [p["date"] for p in out4["daily"]] == ["2026-09-16"]


def test_build_trend_pure_function():
    """纯函数级：窗口含上下界（start ≤ d ≤ today）、周一锚点、差分。"""
    rows = [
        StatusSnapshot(snapshot_date=date(2026, 9, 7), metrics={"started_projects_total": 10}),   # 周一
        StatusSnapshot(snapshot_date=date(2026, 9, 12), metrics={"started_projects_total": 14}),  # 周六
        StatusSnapshot(snapshot_date=date(2026, 9, 14), metrics={"started_projects_total": 20}),  # 下周一
    ]
    out = build_trend(rows, days=30, today=date(2026, 9, 18))
    assert [w["week_start"] for w in out["weekly"]] == ["2026-09-07", "2026-09-14"]
    assert out["weekly"][0]["metrics"]["started_projects_total"] == 14  # 周内最后一个
    assert out["weekly"][1]["delta"]["started_projects_total"] == 6
    assert out["weekly"][0]["delta"]["started_projects_total"] == 0

    # future 行（> today）不入窗口
    future = StatusSnapshot(snapshot_date=date(2026, 9, 19), metrics={})
    out2 = build_trend(rows + [future], days=30, today=date(2026, 9, 18))
    assert all(p["date"] <= "2026-09-18" for p in out2["daily"])

    # 空数据
    out3 = build_trend([], days=30, today=date(2026, 9, 18))
    assert out3["daily"] == [] and out3["weekly"] == []


# ---------- 权限与校验 ----------

def test_snapshot_run_requires_admin(client, db_session):
    """run 仅 admin（403）；trend 登录即可（工程师 200）。"""
    from app.core.security import hash_password
    from app.models import User

    db_session.add(User(username="snapshot_eng", name="快照工程师", role="engineer",
                        password_hash=hash_password("engpass"), must_change_password=False))
    db_session.commit()
    client.post("/api/auth/login", json={"username": "snapshot_eng", "password": "engpass"})

    assert client.post("/api/analysis/snapshots/run").status_code == 403
    assert client.get("/api/analysis/trend?days=30").status_code == 200


def test_trend_days_validation(client):
    """days 仅支持 30/90/180。"""
    assert client.get("/api/analysis/trend?days=45").status_code == 400
    assert client.get("/api/analysis/trend?days=90").status_code == 200


def test_trend_empty(client):
    """无快照时返回空点位（前端显示空态提示）。"""
    data = client.get("/api/analysis/trend?days=30").json()
    assert data["daily"] == []
    assert data["weekly"] == []
