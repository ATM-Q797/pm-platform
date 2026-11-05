"""看板增强测试：T5 阶段级延期/即将到期/冲突计数 + 8-1 风险队列/周差分/环比。

日期用例基于相对今天构造，避免时间漂移。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models import Phase, Project, Resource, StatusSnapshot
from app.services.snapshot import build_trend


def _today() -> date:
    return date.today()


def _mk_project(db_session, name: str) -> Project:
    p = Project(code=str(len(list(db_session.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区")
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, start: date, end: date,
              status: str = "进行中") -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50)
    db_session.add(ph)
    db_session.flush()
    return ph


def test_delayed_phases_detected(client, db_session):
    """阶段级延期：plan_end < 今天且未完成；已完成/搁置不算。"""
    t = _today()
    p = _mk_project(db_session, "延期项目")
    late = _mk_phase(db_session, p, "已逾期", t - timedelta(days=10), t - timedelta(days=3))
    done = _mk_phase(db_session, p, "已完成逾期", t - timedelta(days=20), t - timedelta(days=10), status="已完成")
    blocked = _mk_phase(db_session, p, "搁置逾期", t - timedelta(days=20), t - timedelta(days=10), status="搁置")
    _mk_phase(db_session, p, "未到期", t + timedelta(days=5), t + timedelta(days=15))
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    names = [d["phase_name"] for d in data["delayed_phases"]]
    assert names == ["已逾期"]  # 只含活跃状态的逾期阶段
    late_info = next(d for d in data["delayed_phases"] if d["phase_name"] == "已逾期")
    assert late_info["overdue_days"] == 3
    assert late_info["project_name"] == "延期项目"
    assert late_info["phase_id"] == late.id


def test_delayed_phases_sorted_by_overdue(client, db_session):
    """延期阶段按逾期天数倒序。"""
    t = _today()
    p = _mk_project(db_session, "排序项目")
    _mk_phase(db_session, p, "逾期2天", t - timedelta(days=5), t - timedelta(days=2))
    _mk_phase(db_session, p, "逾期5天", t - timedelta(days=8), t - timedelta(days=5))
    _mk_phase(db_session, p, "逾期10天", t - timedelta(days=15), t - timedelta(days=10))
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    days = [d["overdue_days"] for d in data["delayed_phases"]]
    assert days == sorted(days, reverse=True)
    assert days == [10, 5, 2]


def test_due_soon_phases_detected(client, db_session):
    """即将到期：未来 7 天内到期且未完成。"""
    t = _today()
    p = _mk_project(db_session, "到期项目")
    soon3 = _mk_phase(db_session, p, "3天后到期", t, t + timedelta(days=3))
    _mk_phase(db_session, p, "今天到期", t - timedelta(days=5), t)
    _mk_phase(db_session, p, "8天后到期", t, t + timedelta(days=8))
    _mk_phase(db_session, p, "已完成即将", t, t + timedelta(days=2), status="已完成")
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    names = [d["phase_name"] for d in data["due_soon_phases"]]
    assert names == ["今天到期", "3天后到期"]  # 升序：剩余天数少在前
    assert data["due_soon_count"] == 2
    soon = next(d for d in data["due_soon_phases"] if d["phase_name"] == "3天后到期")
    assert soon["days_left"] == 3
    assert soon["phase_id"] == soon3.id


def test_conflict_count_matches_t4(client, db_session):
    """conflict_count 与 T4 冲突对数一致。"""
    t = _today()
    r = Resource(name="冲突人")
    db_session.add(r)
    db_session.flush()
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    a = _mk_phase(db_session, p1, "阶段一", t, t + timedelta(days=20))          # 20 天
    b = _mk_phase(db_session, p2, "阶段二", t + timedelta(days=8), t + timedelta(days=28))  # 重叠 12 天 ≥ 10 且 ≥ 12 ✅
    a.assignees = [r]
    b.assignees = [r]
    # 并行数推到 4 → 报冲突（2 个干扰阶段与窗口重叠）
    for i in range(2):
        p3 = _mk_project(db_session, f"并行项目{i + 1}")
        ph = _mk_phase(db_session, p3, f"并行阶段{i + 1}", t, t + timedelta(days=28))
        ph.assignees = [r]
    db_session.commit()

    stats = client.get("/api/dashboard/stats").json()
    conflicts = client.get("/api/resources/conflicts").json()
    t4_pairs = sum(len(rc["conflicts"]) for rc in conflicts)
    assert stats["conflict_count"] == t4_pairs == 6  # 4 阶段两两组合


def test_no_risk_data_empty_lists(client, db_session):
    """无延期/到期/冲突时返回空列表与 0 计数。"""
    t = _today()
    p = _mk_project(db_session, "正常项目")
    _mk_phase(db_session, p, "进行中", t, t + timedelta(days=30))
    _mk_phase(db_session, p, "已完成", t - timedelta(days=30), t - timedelta(days=10), status="已完成")
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    assert data["delayed_phases"] == []
    assert data["due_soon_phases"] == []
    assert data["due_soon_count"] == 0
    assert data["conflict_count"] == 0


# ---------- 8-1 数据看板增强：风险队列合并去重 + 周差分/环比 ----------

def _mk_conflict_cluster(db_session, prefix: str, resources: list[Resource], t: date) -> None:
    """4 个项目各 1 个深度重叠阶段挂到给定资源——峰值并行 4 > 3 触发冲突。

    区间设计产生 5 对（重叠 20/20/12/12/12）：两两 ≥ 10 天且 ≥ 短者 60%（B-C 仅重叠 4 天不成对）。
    同批阶段挂多个资源时每人各报 5 对（跨资源重复），供去重用例。
    """
    ranges = [(t, t + timedelta(days=20)), (t + timedelta(days=8), t + timedelta(days=28)),
              (t, t + timedelta(days=12)), (t, t + timedelta(days=28))]
    for i, (start, end) in enumerate(ranges):
        p = _mk_project(db_session, f"{prefix}项目{i + 1}")
        ph = _mk_phase(db_session, p, f"{prefix}阶段{i + 1}", start, end)
        ph.assignees = resources
    db_session.flush()


def test_risk_queue_merge_dedup(client, db_session):
    """三源合并去重：同冲突对跨资源合 1 行（资源并入 detail）；分组顺序 逾期 → 冲突 → 到期。"""
    t = _today()
    r1, r2 = Resource(name="资源甲"), Resource(name="资源乙")
    db_session.add_all([r1, r2])
    db_session.flush()

    p1 = _mk_project(db_session, "逾期项目")
    _mk_phase(db_session, p1, "逾期阶段", t - timedelta(days=12), t - timedelta(days=2))  # 逾期 2 天
    p2 = _mk_project(db_session, "到期项目")
    _mk_phase(db_session, p2, "到期阶段", t - timedelta(days=1), t + timedelta(days=3))  # 剩 3 天

    _mk_conflict_cluster(db_session, "冲突", [r1, r2], t)
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    queue = data["risk_queue"]
    assert [r["type"] for r in queue] == ["overdue"] + ["conflict"] * 5 + ["due_soon"]
    assert len(queue) == 7  # 三来源合并去重后总数（2 资源 × 5 对 → 5 行冲突）

    # 同一冲突对跨资源只算 1 行，两个资源名并入 detail
    for row in (r for r in queue if r["type"] == "conflict"):
        assert "资源甲" in row["detail"] and "资源乙" in row["detail"]
    # 卡面 conflict_count 仍按资源计（T4 口径：2 人 × 5 对 = 10）；队列去重后 5
    assert data["conflict_count"] == 10

    # 点行跳项目详情：project_id 为真实项目，days/detail 与来源同口径
    overdue_row = queue[0]
    assert overdue_row["project_id"] == p1.id and overdue_row["days"] == 2
    assert overdue_row["detail"] == "阶段逾期 2 天"
    due_row = queue[-1]
    assert due_row["project_id"] == p2.id and due_row["days"] == 3
    assert due_row["detail"] == "剩余 3 天到期"


def test_risk_queue_group_sorting(client, db_session):
    """组内排序（2026-11-04 裁定）：逾期天数降序 → 冲突重叠降序 → 到期剩余升序。"""
    t = _today()
    p = _mk_project(db_session, "排序风险项目")
    _mk_phase(db_session, p, "逾期10天", t - timedelta(days=12), t - timedelta(days=10))
    _mk_phase(db_session, p, "逾期5天", t - timedelta(days=7), t - timedelta(days=5))
    _mk_phase(db_session, p, "剩2天", t - timedelta(days=1), t + timedelta(days=2))
    _mk_phase(db_session, p, "剩5天", t - timedelta(days=2), t + timedelta(days=5))
    r = Resource(name="单资源")
    db_session.add(r)
    db_session.flush()
    _mk_conflict_cluster(db_session, "簇", [r], t)
    db_session.commit()

    queue = client.get("/api/dashboard/stats").json()["risk_queue"]
    assert [x["type"] for x in queue] == ["overdue", "overdue"] + ["conflict"] * 5 + ["due_soon", "due_soon"]
    assert [x["days"] for x in queue] == [10, 5, 20, 20, 12, 12, 12, 2, 5]


def test_risk_queue_cross_type_not_deduped(client, db_session):
    """同一阶段既逾期又卷入冲突 = 两行（跨风险类型不去重，两类风险都要查）。"""
    t = _today()
    r = Resource(name="背锅人")
    db_session.add(r)
    db_session.flush()
    for i in range(4):
        p = _mk_project(db_session, f"交叉项目{i + 1}")
        ph = _mk_phase(db_session, p, f"交叉阶段{i + 1}", t - timedelta(days=25), t - timedelta(days=5))
        ph.assignees = [r]
    db_session.commit()

    queue = client.get("/api/dashboard/stats").json()["risk_queue"]
    types = [x["type"] for x in queue]
    assert types.count("overdue") == 4  # 4 个逾期阶段各 1 行
    assert types.count("conflict") == 6  # 4 阶段两两深度重叠 6 对（单资源无跨资源重复）
    assert len(queue) == 10  # 跨类型不去重：逾期行与冲突行并存
    # 交叉证据：交叉阶段1 既有逾期行，又出现在冲突行中
    assert "交叉阶段1" in {x["phase_name"] for x in queue if x["type"] == "overdue"}
    conflict_text = " ".join(x["phase_name"] + x["detail"] for x in queue if x["type"] == "conflict")
    assert "交叉阶段1" in conflict_text


def test_weekly_delta_new_keys():
    """8-1：_WEEKLY_DELTA_KEYS 新增 delayed_phases/conflict_pairs，周差分与快照值同源。"""
    t = _today()
    monday0 = t - timedelta(days=t.weekday())
    last_monday = monday0 - timedelta(days=7)
    rows = [
        StatusSnapshot(snapshot_date=last_monday, metrics={"delayed_phases": 4, "conflict_pairs": 6}),
        StatusSnapshot(snapshot_date=last_monday + timedelta(days=6), metrics={"delayed_phases": 5, "conflict_pairs": 6}),
        StatusSnapshot(snapshot_date=t, metrics={"delayed_phases": 2, "conflict_pairs": 9}),
    ]
    out = build_trend(rows, days=30, today=t)
    assert [w["delta"]["delayed_phases"] for w in out["weekly"]] == [0, -3]  # 本周 2 − 上周 5
    assert [w["delta"]["conflict_pairs"] for w in out["weekly"]] == [0, 3]


def test_stats_weekly_delta_and_snapshot_date(client, db_session):
    """8-1：stats 返回 4 卡环比（与 build_trend 同一周差分公式）与数据截至日期；无快照/无基期 → None。"""
    t = _today()
    monday0 = t - timedelta(days=t.weekday())
    last_monday = monday0 - timedelta(days=7)

    # 无快照：空态（页面不报错，前端显示触发入口）
    data = client.get("/api/dashboard/stats").json()
    assert data["snapshot_date"] is None
    assert data["weekly_delta"] is None

    db_session.add(StatusSnapshot(snapshot_date=last_monday, metrics={
        "projects_total": 10, "delayed_projects": 1, "due_soon_phases": 2, "conflict_pairs": 3,
    }))
    db_session.commit()
    data = client.get("/api/dashboard/stats").json()
    assert data["snapshot_date"] == last_monday.isoformat()
    assert data["weekly_delta"] is None  # 仅一周快照，无对比基期——不用 0 冒充无变化

    db_session.add(StatusSnapshot(snapshot_date=t, metrics={
        "projects_total": 12, "delayed_projects": 0, "due_soon_phases": 4, "conflict_pairs": 3,
    }))
    db_session.commit()
    data = client.get("/api/dashboard/stats").json()
    assert data["snapshot_date"] == t.isoformat()
    assert data["weekly_delta"] == {
        "projects_total": 2, "delayed_projects": -1, "due_soon_phases": 2, "conflict_pairs": 0,
    }

