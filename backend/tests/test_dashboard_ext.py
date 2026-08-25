"""看板增强（T5）测试：阶段级延期 / 即将到期 / 冲突计数。

日期用例基于相对今天构造，避免时间漂移。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models import Phase, Project, Resource


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
    """阶段级延期：plan_end < 今天且未完成；已完成/已搁置不算。"""
    t = _today()
    p = _mk_project(db_session, "延期项目")
    late = _mk_phase(db_session, p, "已逾期", t - timedelta(days=10), t - timedelta(days=3))
    done = _mk_phase(db_session, p, "已完成逾期", t - timedelta(days=20), t - timedelta(days=10), status="已完成")
    blocked = _mk_phase(db_session, p, "搁置逾期", t - timedelta(days=20), t - timedelta(days=10), status="已搁置")
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
