"""8-3 项目趋势测试（PHASE8_PLAN §三；批次档 项目趋势-2026-11-10 §2 验收①~⑦）。

覆盖（验收七条 → 用例映射）：
- ①当日末点与看板当日数字一致 → test_snapshot_projects_today_* 四键载荷与定格
- ②停机缺口断开非补零 → test_trend_gap_breaks_not_zero_filled
- ③同日重复触发不两行 → test_upsert_same_day_idempotent（+ 唯一约束静态兜底）
- ④被删项目按编号可查 → test_trend_by_code_deleted_project
- ⑤三类事件点渲染数据 → test_trend_events_three_kinds
- ⑥数据 <7 天「积累中」→ 前端展示逻辑（RT-11 断言），此处验端点契约（空点列/点数）
- ⑦降采样边界（周周一锚点/月月初锚点、粒度切换连续）→ test_build_project_trend_granularity_markers
读口径：专项 403 / 搁置 frozen / by-code 路径 / days 校验。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from app.models import DataChangeEvent, Phase, Project, ProjectSnapshot
from app.services.snapshot import (
    build_project_events,
    build_project_trend,
    collect_project_metrics,
    snapshot_projects_today,
)


def _mk_project(db, name: str, *, code: str | None = None, is_special: bool = False,
                status: str = "进行中") -> Project:
    p = Project(code=code or str(len(list(db.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区", status=status,
                is_special=is_special)
    db.add(p)
    db.flush()
    return p


def _mk_phase(db, project: Project, name: str, start: date, end: date,
              status: str = "进行中", progress: int = 50,
              actual_end: date | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=progress,
               actual_end=actual_end)
    db.add(ph)
    db.flush()
    return ph


# ---------- 采集：四键载荷与定格 ----------

def test_collect_project_metrics_four_keys(db_session):
    """四键载荷口径：计划/实际累计完成度、延期阶段数、冲突对数（验收①同源计数）。"""
    t = date.today()
    p = _mk_project(db_session, "趋势项目")
    # 3 阶段：1 已按期完成（actual_end=t-1）、1 计划已过未完成（延期）、1 计划在未来
    _mk_phase(db_session, p, "已完成阶段", t - timedelta(days=10), t - timedelta(days=1),
              status="已完成", actual_end=t - timedelta(days=1))
    _mk_phase(db_session, p, "延期阶段", t - timedelta(days=20), t - timedelta(days=5))  # plan_end < today 未完成
    _mk_phase(db_session, p, "未来阶段", t + timedelta(days=1), t + timedelta(days=10))
    db_session.commit()

    m = collect_project_metrics(db_session, p, today=t)
    # 计划累计：3 阶段中按计划应已完成 1（t-1 ≤ t），未完成但计划已过的「延期阶段」计划口径也算应完成 → 2/3 = 67
    assert m["plan_cum_pct"] == 67
    # 实际累计：已完成 1/3 = 33
    assert m["actual_cum_pct"] == 33
    # 延期阶段数：计划已过且未完成 1（与 dashboard 延期判定同族口径）
    assert m["delayed_phases"] == 1
    # 无冲突构造 → 0
    assert m["conflict_pairs"] == 0


def test_collect_project_metrics_no_phases_null(db_session):
    """无阶段项目：四键置 None（缺键/缺数据不冒充 0）。"""
    p = _mk_project(db_session, "无阶段项目")
    db_session.commit()
    m = collect_project_metrics(db_session, p, today=date.today())
    assert m == {
        "plan_cum_pct": None,
        "actual_cum_pct": None,
        "delayed_phases": None,
        "conflict_pairs": None,
    }


def test_snapshot_projects_today_scopes_and_payload(client, db_session):
    """只拍在办（未开始/进行中），专项排除、搁置/完成不拍；payload 四键 + 粒度标记 day。"""
    t = date.today()
    inprog = _mk_project(db_session, "进行中项目")
    notstarted = _mk_project(db_session, "未开始项目", status="未开始")
    _mk_project(db_session, "搁置项目", status="搁置")
    _mk_project(db_session, "已完成项目", status="已完成")
    _mk_project(db_session, "专项项目", is_special=True)
    db_session.commit()

    snap_count, created = snapshot_projects_today(db_session, today=t)
    assert (snap_count, created) == (2, 2)  # 在办 2 个，全部新建

    rows = db_session.scalars(
        select(ProjectSnapshot).where(ProjectSnapshot.snapshot_date == t)
    ).all()
    assert len(rows) == 2
    by_code = {r.project_code: r for r in rows}
    # 只拍在办：进行中 + 未开始；搁置/已完成/专项不拍
    assert set(by_code) == {inprog.code, notstarted.code}
    row = by_code[inprog.code]
    assert row.metrics["_granularity"] == "day"
    assert set(row.metrics) == {"plan_cum_pct", "actual_cum_pct", "delayed_phases", "conflict_pairs", "_granularity"}
    assert row.project_name == "进行中项目"  # 冗余身份字段随拍定格


# ---------- upsert 幂等（验收③） ----------

def test_upsert_same_day_idempotent(client, db_session):
    """同日重复触发不产生两行：第二次触发覆盖当日行（created=0），行数恒 1。"""
    t = date.today()
    p = _mk_project(db_session, "幂等项目")
    _mk_phase(db_session, p, "阶段乙", t - timedelta(days=3), t + timedelta(days=3))
    db_session.commit()

    n1, created1 = snapshot_projects_today(db_session, today=t)
    assert created1 == 1
    # 项目中途新增阶段 → 二次触发覆盖当日行为最新值（upsert 语义）
    _mk_phase(db_session, p, "阶段丙", t, t + timedelta(days=5))
    db_session.commit()
    n2, created2 = snapshot_projects_today(db_session, today=t)
    assert created2 == 0  # 覆盖不算新建

    count = db_session.scalar(
        select(func.count()).select_from(ProjectSnapshot).where(
            ProjectSnapshot.project_id == p.id,
            ProjectSnapshot.snapshot_date == t,
        )
    )
    assert count == 1  # ③同日重复触发不产生两行
    row = db_session.scalar(
        select(ProjectSnapshot).where(
            ProjectSnapshot.project_id == p.id,
            ProjectSnapshot.snapshot_date == t,
        )
    )
    assert row.metrics["actual_cum_pct"] == 0  # 3 阶段 0 完成 = 0%


def test_upsert_unique_constraint_backstop(db_session):
    """唯一约束 (project_id, snapshot_date) 兜底：绕过服务层直插同行 → IntegrityError。"""
    from sqlalchemy.exc import IntegrityError

    t = date.today()
    p = _mk_project(db_session, "约束项目")
    db_session.add(ProjectSnapshot(
        project_id=p.id, snapshot_date=t,
        metrics={"plan_cum_pct": 0, "actual_cum_pct": 0, "delayed_phases": 0, "conflict_pairs": 0},
        project_code=p.code, project_name=p.name,
    ))
    db_session.commit()
    db_session.add(ProjectSnapshot(
        project_id=p.id, snapshot_date=t, metrics={},
        project_code=p.code, project_name=p.name,
    ))
    try:
        db_session.commit()
        assert False, "唯一约束未生效——同日两行插入成功"
    except IntegrityError:
        db_session.rollback()


# ---------- 读端点：混合点列 / 缺口断开 / 读口径 ----------

def test_trend_endpoint_mixed_points_and_gap(client, db_session):
    """trend 端点混合点列 + 停机缺口断开非补零（验收②）+ days 校验 + 未登录 401。"""
    t = date.today()
    p = _mk_project(db_session, "缺口项目")
    db_session.commit()
    # 三个快照日：今天、4 天前、10 天前（中间停机）——粒度标记 day
    for d in (t, t - timedelta(days=4), t - timedelta(days=10)):
        db_session.add(ProjectSnapshot(
            project_id=p.id, snapshot_date=d,
            metrics={"plan_cum_pct": 50, "actual_cum_pct": 33,
                     "delayed_phases": 1, "conflict_pairs": 0, "_granularity": "day"},
            project_code=p.code, project_name=p.name,
        ))
    db_session.commit()

    r = client.get(f"/api/projects/{p.id}/trend?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 30
    assert body["frozen"] is False
    assert [pt["date"] for pt in body["points"]] == [
        (t - timedelta(days=10)).isoformat(),
        (t - timedelta(days=4)).isoformat(),
        t.isoformat(),
    ]
    # 缺口断开非补零：点列只有真实快照日，无中间补零日
    dates = {pt["date"] for pt in body["points"]}
    assert (t - timedelta(days=1)).isoformat() not in dates
    assert (t - timedelta(days=2)).isoformat() not in dates
    # 粒度标记随点携带；metrics 四键齐全
    assert all(pt["granularity"] == "day" for pt in body["points"])
    assert all(set(pt["metrics"]) == {"plan_cum_pct", "actual_cum_pct", "delayed_phases", "conflict_pairs"}
               for pt in body["points"])

    # days 非法 400；未登录 401
    assert client.get(f"/api/projects/{p.id}/trend?days=45").status_code == 400
    assert client.get(f"/api/projects/{p.id}/trend?days=365").status_code == 200
    from app.core.security import COOKIE_NAME, decode_access_token
    # TestClient 保留 cookie：用无 cookie 的独立客户端验 401
    from fastapi.testclient import TestClient as _TC
    from app.main import app as _app
    bare = _TC(_app)
    assert bare.get(f"/api/projects/{p.id}/trend?days=30").status_code == 401


def test_trend_special_403_and_shelved_frozen(client, db_session):
    """读口径：专项 403（循 health 端点先例——非 admin/manager 一律 403）；搁置返回冻结前历史（frozen=true + frozen_date）。"""
    t = date.today()
    special = _mk_project(db_session, "专项趋势", is_special=True)
    shelved = _mk_project(db_session, "搁置趋势", status="搁置")
    db_session.commit()
    frozen_day = t - timedelta(days=2)
    db_session.add(ProjectSnapshot(
        project_id=shelved.id, snapshot_date=frozen_day,
        metrics={"plan_cum_pct": 33, "actual_cum_pct": 33, "delayed_phases": 0,
                 "conflict_pairs": 0, "_granularity": "day"},
        project_code=shelved.code, project_name="搁置趋势",
    ))
    db_session.commit()

    # 专项：admin/manager 可读（check_special_project_access 先例——与详情/health 同族），
    # viewer/engineer 一律 403
    assert client.get(f"/api/projects/{special.id}/trend?days=30").status_code == 200  # admin
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="trend_eng", name="趋势工程师", role="engineer",
                        password_hash=hash_password("engpass"), must_change_password=False))
    db_session.commit()
    client.post("/api/auth/login", json={"username": "trend_eng", "password": "engpass"})
    assert client.get(f"/api/projects/{special.id}/trend?days=30").status_code == 403

    # 搁置：200 + frozen 标记 + 冻结日 = 最后一个快照日
    r2 = client.get(f"/api/projects/{shelved.id}/trend?days=30")
    assert r2.status_code == 200
    body = r2.json()
    assert body["frozen"] is True
    assert body["frozen_date"] == frozen_day.isoformat()
    assert len(body["points"]) == 1  # 冻结前历史正常返回


def test_trend_by_code_deleted_project(client, db_session):
    """by-code 路径（验收④）：被删项目 project_id SET NULL 后按编号寻址；viewer 403。"""
    t = date.today()
    p = _mk_project(db_session, "将删项目")
    db_session.commit()
    for d, actual in ((t - timedelta(days=1), 33), (t, 67)):
        db_session.add(ProjectSnapshot(
            project_id=p.id, snapshot_date=d,
            metrics={"plan_cum_pct": actual, "actual_cum_pct": actual, "delayed_phases": 0,
                     "conflict_pairs": 0, "_granularity": "day"},
            project_code=p.code, project_name="将删项目",
        ))
    db_session.commit()

    # 删项目（模拟物理删除 → project_id 全部 SET NULL，行保留）
    pid = p.id
    code = p.code
    db_session.delete(p)
    db_session.commit()
    rows = db_session.scalars(
        select(ProjectSnapshot).where(ProjectSnapshot.project_code == code)
    ).all()
    assert len(rows) == 2 and all(r.project_id is None for r in rows)  # SET NULL 生效、行保留

    # admin 按编号查到被删项目曲线
    r = client.get(f"/api/projects/by-code/{code}/trend?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] is None  # 被删项目 project_id 为空
    assert body["project_code"] == code
    assert body["project_name"] == "将删项目"  # 名字冻结在删除时刻
    assert len(body["points"]) == 2
    assert body["points"][-1]["metrics"]["actual_cum_pct"] == 67

    # 不存在的编号 404
    assert client.get("/api/projects/by-code/NOPE/trend").status_code == 404

    # 非 admin 403（admin「历史项目」入口，require_role("admin")）
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="trend_viewer", name="趋势观察员", role="viewer",
                        password_hash=hash_password("viewpass"), must_change_password=False))
    db_session.commit()
    client.post("/api/auth/login", json={"username": "trend_viewer", "password": "viewpass"})
    assert client.get(f"/api/projects/by-code/{code}/trend").status_code == 403


# ---------- 事件点（验收⑤）与降采样边界（验收⑦） ----------

def test_trend_events_three_kinds(client, db_session):
    """三类事件点：延期/冲突取自快照 metrics>0；计划变更取自 data_change_events（field 白名单）。"""
    t = date.today()
    p = _mk_project(db_session, "事件项目")
    db_session.commit()
    db_session.add(ProjectSnapshot(
        project_id=p.id, snapshot_date=t - timedelta(days=1),
        metrics={"plan_cum_pct": 33, "actual_cum_pct": 33, "delayed_phases": 2,
                 "conflict_pairs": 1, "_granularity": "day"},
        project_code=p.code, project_name="事件项目",
    ))
    db_session.add(ProjectSnapshot(
        project_id=p.id, snapshot_date=t,
        metrics={"plan_cum_pct": 67, "actual_cum_pct": 33, "delayed_phases": 0,
                 "conflict_pairs": 0, "_granularity": "day"},
        project_code=p.code, project_name="事件项目",
    ))
    db_session.add(DataChangeEvent(
        project_id=p.id, field="plan_end", old_value="2026-10-01", new_value="2026-10-05",
        source="direct_edit", changed_by_name="张三", project_name="事件项目",
    ))
    db_session.add(DataChangeEvent(
        project_id=p.id, field="phase_plan_start", old_value="2026-09-01", new_value="2026-09-05",
        source="report_edit", changed_by_name="李四", project_name="事件项目", phase_name="阶段甲",
    ))
    db_session.commit()

    r = client.get(f"/api/projects/{p.id}/trend?days=30")
    assert r.status_code == 200
    events = r.json()["events"]

    delayed = [e for e in events if e["kind"] == "delayed"]
    conflict = [e for e in events if e["kind"] == "conflict"]
    plan_change = [e for e in events if e["kind"] == "plan_change"]
    assert len(delayed) == 1 and delayed[0]["detail"] == "2 个阶段延期"
    assert len(conflict) == 1 and conflict[0]["detail"] == "1 对资源冲突"
    # 项目级计划变更事件（plan_end）入点；阶段级（phase_plan_start）不入——批次档口径 field ∈ {plan_start, plan_end}
    assert len(plan_change) == 1
    assert plan_change[0]["detail"] == "项目计划结束 2026-10-01 → 2026-10-05（张三）"
    assert plan_change[0]["date"] == t.isoformat()  # created_at=今天（server_default）


def test_build_project_trend_granularity_markers():
    """降采样边界（验收⑦）：周行周一锚点 / 月行月初锚点；粒度切换处曲线连续（点列统一透出）。

    降采样写侧由 PG 函数 maintain_project_snapshots 执行（migrate_v6.sql 静态核验）；
    读侧行带 _granularity 标记——此处以预制三种粒度行验证混合点列契约。
    """
    t = date.today()
    month_row = t - timedelta(days=400)  # 窗口外铺一行作日期锚（月粒度历史）
    week_anchor = month_row - timedelta(days=month_row.weekday())  # 该周周一锚
    rows = [
        # 月行（月初锚点）
        ProjectSnapshot(snapshot_date=date(month_row.year, month_row.month, 1),
                        metrics={"plan_cum_pct": 10, "actual_cum_pct": 10,
                                 "delayed_phases": 0, "conflict_pairs": 0, "_granularity": "month"}),
        # 周行（周一锚点）：与月行同日也合法（月行代表月初、周行代表该周）
        ProjectSnapshot(snapshot_date=week_anchor,
                        metrics={"plan_cum_pct": 20, "actual_cum_pct": 15,
                                 "delayed_phases": 1, "conflict_pairs": 0, "_granularity": "week"}),
        # 日行（近期）
        ProjectSnapshot(snapshot_date=t,
                        metrics={"plan_cum_pct": 50, "actual_cum_pct": 40,
                                 "delayed_phases": 0, "conflict_pairs": 0, "_granularity": "day"}),
    ]
    # 窗口 365+（覆盖全部行）——粒度切换处三类行统一透出、按日期升序
    points = build_project_trend(rows, days=500, today=t)
    assert [(pt["date"], pt["granularity"]) for pt in points] == [
        (date(month_row.year, month_row.month, 1).isoformat(), "month"),
        (week_anchor.isoformat(), "week"),
        (t.isoformat(), "day"),
    ]
    # 四键齐全、_granularity 不外泄
    assert all(set(pt["metrics"]) == {"plan_cum_pct", "actual_cum_pct", "delayed_phases", "conflict_pairs"}
               for pt in points)
    # 窗口过滤：days=1 只留今天
    points_1d = build_project_trend(rows, days=1, today=t)
    assert [pt["date"] for pt in points_1d] == [t.isoformat()]


def test_trend_endpoint_frozen_events_by_code_deleted(client, db_session):
    """被删项目的计划变更事件仍可查（by-code 路径 + project_name 冗余匹配）。"""
    t = date.today()
    p = _mk_project(db_session, "删后事件项目")
    db_session.commit()
    db_session.add(ProjectSnapshot(
        project_id=p.id, snapshot_date=t - timedelta(days=1),
        metrics={"plan_cum_pct": 33, "actual_cum_pct": 33, "delayed_phases": 0,
                 "conflict_pairs": 0, "_granularity": "day"},
        project_code=p.code, project_name="删后事件项目",
    ))
    db_session.add(DataChangeEvent(
        project_id=p.id, field="plan_start", old_value="2026-09-01", new_value="2026-09-08",
        source="direct_edit", changed_by_name="王五", project_name="删后事件项目",
    ))
    db_session.commit()
    code = p.code
    db_session.delete(p)
    db_session.commit()

    r = client.get(f"/api/projects/by-code/{code}/trend?days=30")
    assert r.status_code == 200
    plan_change = [e for e in r.json()["events"] if e["kind"] == "plan_change"]
    assert len(plan_change) == 1
    assert plan_change[0]["detail"] == "项目计划开始 2026-09-01 → 2026-09-08（王五）"
