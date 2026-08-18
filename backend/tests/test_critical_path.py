"""关键路径（CPM）算法测试。

构造真实 ORM 数据（内存 SQLite），直接调用 compute_critical_path 验证。
"""
from __future__ import annotations

from datetime import date

from app.models import Dependency, Phase, Project
from app.services.critical_path import compute_critical_path


def _make_project(db_session, phases: list[tuple[str, date, date]], deps: list[tuple[int, int]]) -> tuple[Project, list[Phase]]:
    """构造项目：phases = [(name, plan_start, plan_end)]，deps = [(from_idx, to_idx)]。"""
    project = Project(
        code=f"CPM-{len(list(db_session.query(Project))) + 1}",
        category="新需求",
        name="关键路径测试项目",
        owner="测试",
        market="拉美区",
    )
    db_session.add(project)
    db_session.flush()

    phase_objs: list[Phase] = []
    for i, (name, start, end) in enumerate(phases, start=1):
        ph = Phase(
            project_id=project.id,
            phase_type=f"P{i}",
            name=name,
            sequence=i,
            plan_start=start,
            plan_end=end,
            status="未开始",
        )
        db_session.add(ph)
        db_session.flush()
        phase_objs.append(ph)

    for fi, ti in deps:
        db_session.add(Dependency(
            from_phase_id=phase_objs[fi].id,
            to_phase_id=phase_objs[ti].id,
            type="FS",
            lag_days=0,
        ))
    db_session.commit()
    return project, phase_objs


def _ids(phases: list[Phase], *indices: int) -> list[int]:
    return [phases[i].id for i in indices]


def test_chain_all_critical(db_session):
    """链式依赖 A→B→C：全部在关键路径上，总工期 = 三段之和。"""
    p, ph = _make_project(db_session, [
        ("需求评估", date(2026, 7, 1), date(2026, 7, 3)),   # 2 天
        ("结构设计", date(2026, 7, 3), date(2026, 7, 6)),   # 3 天
        ("联调测试", date(2026, 7, 6), date(2026, 7, 9)),   # 3 天
    ], [(0, 1), (1, 2)])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == _ids(ph, 0, 1, 2)
    assert r.total_duration == 8
    assert r.path == ["需求评估", "结构设计", "联调测试"]


def test_parallel_branch_only_longest_critical(db_session):
    """A→B(长) 与 A→C(短) 并行：B 是关键路径，C 有浮动不算。"""
    p, ph = _make_project(db_session, [
        ("工业设计", date(2026, 7, 1), date(2026, 7, 3)),   # 2 天
        ("结构设计", date(2026, 7, 3), date(2026, 7, 10)),  # 7 天（长）
        ("样机打样", date(2026, 7, 3), date(2026, 7, 5)),   # 2 天（短）
    ], [(0, 1), (0, 2)])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == _ids(ph, 0, 1)
    assert r.total_duration == 9
    assert r.path == ["工业设计", "结构设计"]


def test_no_dependency_longest_only(db_session):
    """无依赖项目：只有工期最长的阶段是关键路径（标准 CPM）。"""
    p, ph = _make_project(db_session, [
        ("阶段A", date(2026, 7, 1), date(2026, 7, 4)),   # 3 天
        ("阶段B", date(2026, 7, 1), date(2026, 7, 3)),   # 2 天（浮动 1 天）
    ], [])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == [ph[0].id]
    assert r.total_duration == 3


def test_no_dependency_equal_duration_all_critical(db_session):
    """无依赖且工期相同：都是关键路径。"""
    p, ph = _make_project(db_session, [
        ("阶段A", date(2026, 7, 1), date(2026, 7, 4)),
        ("阶段B", date(2026, 7, 1), date(2026, 7, 4)),
    ], [])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == _ids(ph, 0, 1)
    assert r.total_duration == 3


def test_missing_date_phase_skipped(db_session):
    """无计划日期的阶段被跳过，不参与关键路径。"""
    p, ph = _make_project(db_session, [
        ("有日期", date(2026, 7, 1), date(2026, 7, 5)),   # 4 天
        ("无日期", None, None),
    ], [(0, 1)])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == [ph[0].id]
    assert r.total_duration == 4
    assert r.path == ["有日期"]


def test_same_day_duration_min_one(db_session):
    """同一天开始结束：工期按 1 天。"""
    p, ph = _make_project(db_session, [
        ("当天完成", date(2026, 7, 1), date(2026, 7, 1)),
    ], [])

    r = compute_critical_path(db_session, p.id)
    assert r.total_duration == 1
    assert r.critical_phase_ids == [ph[0].id]


def test_cycle_dependency_no_crash(db_session):
    """循环依赖（A→B→A）：不崩溃，正常返回结果（环中阶段无有效关键路径定义）。"""
    p, ph = _make_project(db_session, [
        ("阶段A", date(2026, 7, 1), date(2026, 7, 3)),
        ("阶段B", date(2026, 7, 3), date(2026, 7, 6)),
    ], [(0, 1), (1, 0)])

    r = compute_critical_path(db_session, p.id)
    assert r.total_duration > 0
    assert isinstance(r.critical_phase_ids, list)


def test_empty_project(db_session):
    """项目没有任何阶段：空结果。"""
    p, _ = _make_project(db_session, [], [])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == []
    assert r.total_duration == 0
    assert r.path == []


def test_all_phases_missing_date(db_session):
    """所有阶段都无日期：空结果。"""
    p, _ = _make_project(db_session, [
        ("无日期A", None, None),
        ("无日期B", None, None),
    ], [])

    r = compute_critical_path(db_session, p.id)
    assert r.critical_phase_ids == []
    assert r.total_duration == 0


def test_multi_endpoint_total_duration(db_session):
    """多终点：总工期取最长路径（A→B 与 A→C 并行，B 更长）。"""
    p, ph = _make_project(db_session, [
        ("启动", date(2026, 7, 1), date(2026, 7, 2)),      # 1 天
        ("路径一", date(2026, 7, 2), date(2026, 7, 10)),   # 8 天
        ("路径二", date(2026, 7, 2), date(2026, 7, 4)),    # 2 天
    ], [(0, 1), (0, 2)])

    r = compute_critical_path(db_session, p.id)
    assert r.total_duration == 9
    assert r.critical_phase_ids == _ids(ph, 0, 1)


def test_api_critical_path_endpoint(client, db_session):
    """API 端点：GET /api/projects/{id}/critical-path。"""
    p, ph = _make_project(db_session, [
        ("A", date(2026, 7, 1), date(2026, 7, 3)),
        ("B", date(2026, 7, 3), date(2026, 7, 5)),
    ], [(0, 1)])

    resp = client.get(f"/api/projects/{p.id}/critical-path")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["critical_phase_ids"] == _ids(ph, 0, 1)
    assert data["total_duration"] == 4
    assert data["path"] == ["A", "B"]


def test_api_critical_path_404(client, db_session):
    """不存在的项目返回 404。"""
    resp = client.get("/api/projects/99999/critical-path")
    assert resp.status_code == 404
