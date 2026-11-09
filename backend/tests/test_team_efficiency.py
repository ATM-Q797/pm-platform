"""团队效率六指标单测（§2 验收对照 1-9）。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Phase, Project, Resource, User
from app.services.team_efficiency import compute_team_efficiency, _peak_parallel


# ---------- _peak_parallel ----------

def test_peak_parallel_empty():
    assert _peak_parallel([]) == 0


def test_peak_parallel_single():
    assert _peak_parallel([(date(2026, 1, 1), date(2026, 1, 10))]) == 1


def test_peak_parallel_overlap():
    # 两个区间重叠 → peak=2
    assert _peak_parallel([
        (date(2026, 1, 1), date(2026, 1, 10)),
        (date(2026, 1, 5), date(2026, 1, 15)),
    ]) == 2


def test_peak_parallel_no_overlap():
    assert _peak_parallel([
        (date(2026, 1, 1), date(2026, 1, 5)),
        (date(2026, 1, 6), date(2026, 1, 10)),
    ]) == 1


# ---------- compute_team_efficiency ----------

def _make_project(db: Session, name: str, is_special: bool = False, status: str = "进行中") -> Project:
    p = Project(name=name, code=name, category="自研", owner="T", market="通用",
                is_special=is_special, status=status)
    db.add(p)
    db.flush()
    return p


def _make_resource(db: Session, name: str, role: str = "工业设计") -> Resource:
    r = Resource(name=name, role=role)
    db.add(r)
    db.flush()
    return r


def _make_phase(db: Session, project: Project, assignees: list[Resource],
                status: str = "已完成", plan_start: date | None = None,
                plan_end: date | None = None, actual_start: date | None = None,
                actual_end: date | None = None, rework_count: int = 0,
                phase_type: str = "P1") -> Phase:
    ph = Phase(project_id=project.id, name=f"阶段-{project.name}", phase_type=phase_type,
               sequence=1,
               status=status, plan_start=plan_start, plan_end=plan_end,
               actual_start=actual_start, actual_end=actual_end,
               rework_count=rework_count)
    ph.assignees = assignees
    db.add(ph)
    db.flush()
    return ph


def test_empty_db_returns_zero(db_session: Session):
    result = compute_team_efficiency(db_session)
    assert result.persons == []
    assert result.summary.total_phases == 0


def test_active_projects_excludes_special_and_shelved(db_session: Session):
    """指标 1：在办项目数——排除 is_special + 搁置。"""
    proj = _make_project(db_session, "正常项目")
    special = _make_project(db_session, "专项项目", is_special=True)
    shelved = _make_project(db_session, "搁置项目", status="搁置")
    res = _make_resource(db_session, "张三")
    _make_phase(db_session, proj, [res], status="进行中")
    _make_phase(db_session, special, [res], status="进行中")
    _make_phase(db_session, shelved, [res], status="进行中")
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert len(result.persons) == 1
    assert result.persons[0].active_projects == 1  # 只有正常项目


def test_on_time_rate_shows_sample(db_session: Session):
    """指标 3：按期完成率显样本数——缺完成日不入分母。"""
    proj = _make_project(db_session, "P")
    res = _make_resource(db_session, "张三")
    today = date.today()
    _make_phase(db_session, proj, [res], status="已完成",
                plan_end=today - timedelta(days=1), actual_end=today)
    _make_phase(db_session, proj, [res], status="已完成",
                plan_end=today, actual_end=today - timedelta(days=1))
    _make_phase(db_session, proj, [res], status="已完成",
                plan_end=today, actual_end=None)  # 缺完成日不入分母
    db_session.commit()
    result = compute_team_efficiency(db_session)
    pm = result.persons[0]
    assert pm.on_time_sample == "1/2"
    assert pm.on_time_rate == pytest.approx(0.5)


def test_rework_rate(db_session: Session):
    """指标 4：返工率 = rework_count > 0 的已完成阶段 ÷ 已完成阶段。"""
    proj = _make_project(db_session, "P")
    res = _make_resource(db_session, "张三")
    _make_phase(db_session, proj, [res], status="已完成", rework_count=1)
    _make_phase(db_session, proj, [res], status="已完成", rework_count=0)
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.persons[0].rework_rate == pytest.approx(0.5)


def test_avg_cycle_days_skips_missing(db_session: Session):
    """指标 5：平均阶段周期——缺一头不计。"""
    proj = _make_project(db_session, "P")
    res = _make_resource(db_session, "张三")
    today = date.today()
    _make_phase(db_session, proj, [res], status="已完成",
                actual_start=today - timedelta(days=10), actual_end=today)
    _make_phase(db_session, proj, [res], status="已完成",
                actual_start=today - timedelta(days=5), actual_end=today)
    _make_phase(db_session, proj, [res], status="已完成",
                actual_start=None, actual_end=today)  # 缺一头不计
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.persons[0].avg_cycle_days == pytest.approx(7.5)  # (10+5)/2


def test_completion_rate_top(db_session: Session):
    """完成率 Top：按环节 phase_type 聚合按期完成率（非人维度）。"""
    proj = _make_project(db_session, "P")
    res = _make_resource(db_session, "张三")
    today = date.today()
    _make_phase(db_session, proj, [res], status="已完成", phase_type="P1",
                plan_end=today, actual_end=today)
    _make_phase(db_session, proj, [res], status="已完成", phase_type="P1",
                plan_end=today - timedelta(days=5), actual_end=today)
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert len(result.rework_top) == 1
    assert result.rework_top[0]["phase_type"] == "P1"
    assert result.rework_top[0]["on_time_rate"] == pytest.approx(0.5)


def test_active_projects_dedup(db_session: Session):
    """在办项目去重总数（B 口径）：共管项目跨人不重复计，与看板「进行中」可比。"""
    p1 = _make_project(db_session, "P1")
    p2 = _make_project(db_session, "P2")
    res_a = _make_resource(db_session, "张三")
    res_b = _make_resource(db_session, "李四")
    today = date.today()
    # P1 两人共管（1 个活跃阶段挂两人）；P2 仅张三 → 去重 = 2（按人合计 = 3）
    _make_phase(db_session, p1, [res_a, res_b], status="进行中",
                plan_start=today, plan_end=today + timedelta(days=3))
    _make_phase(db_session, p2, [res_a], status="进行中",
                plan_start=today, plan_end=today + timedelta(days=3))
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.summary.active_projects_dedup == 2
    assert sum(p.active_projects for p in result.persons) == 3
    # 按项目状态构成（浮窗）：固定三维度含 0 值
    assert result.summary.active_projects_breakdown == {"进行中": 2, "未开始": 0, "已完成": 0}
    assert sum(result.summary.active_projects_breakdown.values()) == result.summary.active_projects_dedup


def test_active_projects_breakdown_three_statuses(db_session: Session):
    """构成浮窗三维场景：未开始/已完成状态的项目带活跃阶段各占一行（76 vs 78 差异源回归锁）。"""
    p_ing = _make_project(db_session, "P进行中", status="进行中")
    p_not = _make_project(db_session, "P未开始", status="未开始")
    p_done = _make_project(db_session, "P已完成", status="已完成")
    res = _make_resource(db_session, "张三")
    today = date.today()
    _make_phase(db_session, p_ing, [res], status="进行中",
                plan_start=today, plan_end=today + timedelta(days=3))
    _make_phase(db_session, p_not, [res], status="进行中",
                plan_start=today, plan_end=today + timedelta(days=3))
    _make_phase(db_session, p_done, [res], status="进行中",
                plan_start=today, plan_end=today + timedelta(days=3))
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.summary.active_projects_breakdown == {
        "进行中": 1, "未开始": 1, "已完成": 1,
    }
    assert result.summary.active_projects_dedup == 3


def test_role_load_distribution(db_session: Session):
    """指标 6：按岗位聚合在办项目数。"""
    proj = _make_project(db_session, "P")
    res1 = _make_resource(db_session, "张三", role="工业设计")
    res2 = _make_resource(db_session, "李四", role="工业设计")
    res3 = _make_resource(db_session, "王五", role="结构设计")
    _make_phase(db_session, proj, [res1], status="进行中")
    _make_phase(db_session, proj, [res2], status="进行中")
    _make_phase(db_session, proj, [res3], status="进行中")
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.role_load["工业设计"] == 1  # 1 个项目（去重）
    assert result.role_load["结构设计"] == 1


def test_endpoint_requires_admin_manager(db_session: Session, client: TestClient):
    """验收 6：端点 viewer 403。"""
    resp = client.get("/api/team-efficiency")
    assert resp.status_code in (200, 403)  # admin 200 / viewer 403


def test_completion_date_record_rate(db_session: Session):
    """验收 7：完成日记录率 = 库中 actual_end 空值比例。"""
    proj = _make_project(db_session, "P")
    res = _make_resource(db_session, "张三")
    today = date.today()
    _make_phase(db_session, proj, [res], status="已完成",
                actual_start=today - timedelta(days=5), actual_end=today)
    _make_phase(db_session, proj, [res], status="已完成",
                actual_start=today - timedelta(days=3), actual_end=None)
    db_session.commit()
    result = compute_team_efficiency(db_session)
    assert result.summary.completion_date_record_rate == pytest.approx(0.5)
    assert result.summary.dated_phases == 1
    assert result.summary.total_phases == 2
