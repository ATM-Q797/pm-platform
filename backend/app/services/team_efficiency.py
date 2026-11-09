"""团队效率统计（PHASE8_PLAN §四 8-4）。

零迁移零建表——六指标全部基于 Phase/Resource/Project 现有字段实时计算。
指标计算按人聚合，排除 is_special；搁置项目逐指标处理（见 design §2 搁置项目处理段）。

六指标：
1. 在办项目数 = 该人名下未完成阶段所属项目去重计数（排除 is_special + 搁置）
2. 峰值并行 = 复用 resource_heatmap._peak_parallel(12 周窗内活跃阶段区间)（固定窗，与热力图同口径）
3. 按期完成率 = actual_end ≤ plan_end 的已完成阶段 ÷ 有 actual_end 的已完成阶段（显样本数）
4. 返工率 = rework_count > 0 的阶段 ÷ 已完成阶段
5. 平均阶段周期 = avg(actual_end − actual_start)，缺一头不计
6. 负荷分布 = 按 User.position 岗位聚合在办项目数（回退 Resource.role，看瓶颈岗）

排除规则：is_special=true 项目（一律排除）；无 assignees 的阶段（不计入个人指标）；
非活跃阶段（已完成/搁置）不计入峰值并行。搁置项目按指标分别处理。
指标 1/6 搁置项目排除；指标 3-5 只看已完成阶段（搁置项目内已完成阶段照常入分母）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Phase, Project, Resource, User, phase_assignee


@dataclass
class PersonMetrics:
    resource_id: int
    name: str
    role: str | None
    active_projects: int = 0
    peak_parallel: int = 0
    on_time_rate: float | None = None
    on_time_sample: str = "0/0"
    rework_rate: float | None = None
    avg_cycle_days: float | None = None
    active_phases: int = 0


@dataclass
class EfficiencySummary:
    completion_date_record_rate: float | None = None
    total_phases: int = 0
    dated_phases: int = 0
    active_projects_dedup: int = 0  # 在办项目去重总数（与看板「进行中」可比口径）
    window_label: str = "最近 7 天"


@dataclass
class TeamEfficiency:
    window_days: int
    summary: EfficiencySummary = field(default_factory=EfficiencySummary)
    persons: list[PersonMetrics] = field(default_factory=list)
    role_load: dict[str, int] = field(default_factory=dict)
    rework_top: list[dict] = field(default_factory=list)


def _peak_parallel(intervals: list[tuple[date, date]]) -> int:
    """扫描线求窗口内任意时刻最大同时活跃数（与 resource_heatmap._peak_parallel 同算法）。"""
    if not intervals:
        return 0
    events: list[tuple[date, int]] = []
    for s, e in intervals:
        events.append((s, 1))
        events.append((e, -1))
    events.sort(key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, delta in events:
        cur += delta
        best = max(best, cur)
    return best


def _active_intervals(
    phases: list[Phase], window_start: date, window_end: date
) -> list[tuple[date, date]]:
    """提取窗口内活跃阶段区间（半开区间 [start, end)，只有实际日期用 actual 计入）。"""
    intervals = []
    for ph in phases:
        s = ph.actual_start or ph.plan_start
        e = ph.actual_end or ph.plan_end
        if s is None or e is None:
            continue
        # 裁剪到窗口
        s2 = max(s, window_start)
        e2 = min(e, window_end)
        if s2 < e2:
            intervals.append((s2, e2))
    return intervals


def _project_filters():
    """公共过滤：排除 is_special 和搁置项目。"""
    return (
        Project.is_special == False,  # noqa: E712
        Project.status != "搁置",
    )


def compute_team_efficiency(db: Session, window_days: int = 7) -> TeamEfficiency:
    """计算团队效率六指标。window_days 只影响指标 3-5 的时间范围；指标 2 固定 12 周窗。"""
    today = date.today()
    window_start = today - timedelta(days=window_days)

    # 峰值并行的 12 周固定窗
    peak_window_start = today - timedelta(weeks=12)

    # 拉取所有资源 + 用户岗位（User.position 按姓名匹配，回退 Resource.role）
    resources = db.scalars(select(Resource).order_by(Resource.name)).all()
    if not resources:
        return TeamEfficiency(window_days=window_days)
    # 用户岗位映射（姓名 → position）
    user_positions: dict[str, str | None] = {}
    for u in db.scalars(select(User).where(User.position.isnot(None))):
        user_positions[u.name] = u.position

    # 拉取所有阶段（含项目信息）
    all_phases = db.scalars(
        select(Phase).join(Project, Phase.project_id == Project.id)
    ).all()

    # 按阶段 → 项目映射
    project_map: dict[int, Project] = {}
    for ph in all_phases:
        if ph.project_id not in project_map:
            proj = db.get(Project, ph.project_id)
            if proj:
                project_map[ph.project_id] = proj

    # 有效阶段：排除 is_special 项目
    valid_phases = [
        ph for ph in all_phases
        if ph.project_id in project_map and not project_map[ph.project_id].is_special
    ]

    # 有效项目（排除 is_special + 搁置）——指标 1/6 用
    active_projects_set = {
        ph.project_id for ph in valid_phases
        if ph.status not in ("已完成", "搁置")
        and project_map.get(ph.project_id)
        and project_map[ph.project_id].status != "搁置"
    }

    # 按资源 → 阶段映射（通过 assignees 关系）
    resource_phases: dict[int, list[Phase]] = {r.id: [] for r in resources}
    for ph in valid_phases:
        for ra in ph.assignees:
            if ra.id in resource_phases:
                resource_phases[ra.id].append(ph)

    persons: list[PersonMetrics] = []
    role_project_count: dict[str, set[int]] = {}
    role_phase_count: dict[str, int] = {}
    total_phases = 0
    dated_phases = 0

    for r in resources:
        my_phases = resource_phases.get(r.id, [])
        if not my_phases:
            continue  # 无阶段的人不列入

        pm = PersonMetrics(resource_id=r.id, name=r.name, role=user_positions.get(r.name) or r.role)

        # --- 指标 1: 在办项目数（排除 is_special + 搁置） ---
        my_active_projects = set()
        for ph in my_phases:
            if ph.status in ("已完成", "搁置"):
                continue
            proj = project_map.get(ph.project_id)
            if proj and proj.status != "搁置":
                my_active_projects.add(ph.project_id)
        pm.active_projects = len(my_active_projects)

        # --- 指标 2: 峰值并行（12 周固定窗，非活跃阶段不计入） ---
        active_for_peak = [
            ph for ph in my_phases
            if ph.status not in ("已完成", "搁置")
        ]
        intervals = _active_intervals(active_for_peak, peak_window_start, today)
        pm.peak_parallel = _peak_parallel(intervals)

        # --- 指标 3: 按期完成率（显样本数，缺完成日不入分母） ---
        completed = [ph for ph in my_phases if ph.status == "已完成"]
        with_date = [ph for ph in completed if ph.actual_end is not None]
        on_time = [
            ph for ph in with_date
            if ph.plan_end is not None and ph.actual_end <= ph.plan_end
        ]
        pm.on_time_sample = f"{len(on_time)}/{len(with_date)}"
        if with_date:
            pm.on_time_rate = len(on_time) / len(with_date)

        # --- 指标 4: 返工率 ---
        if completed:
            reworked = sum(1 for ph in completed if ph.rework_count > 0)
            pm.rework_rate = reworked / len(completed)

        # --- 指标 5: 平均阶段周期（缺一头不计） ---
        cycle_days = [
            (ph.actual_end - ph.actual_start).days
            for ph in completed
            if ph.actual_start is not None and ph.actual_end is not None
        ]
        if cycle_days:
            pm.avg_cycle_days = sum(cycle_days) / len(cycle_days)

        # --- 指标 6: 负荷分布（按 User.position 岗位聚合在办项目数，回退 Resource.role） ---
        _pos = user_positions.get(r.name) or r.role
        if _pos:
            if _pos not in role_project_count:
                role_project_count[_pos] = set()
            role_project_count[_pos].update(my_active_projects)
            role_phase_count[_pos] = role_phase_count.get(_pos, 0) + len(
                [ph for ph in my_phases if ph.status not in ("已完成", "搁置")]
            )

        # 汇总统计
        for ph in my_phases:
            total_phases += 1
            if ph.actual_end is not None:
                dated_phases += 1

        pm.active_phases = len(
            [ph for ph in my_phases if ph.status not in ("已完成", "搁置")]
        )
        persons.append(pm)

    # 汇总
    summary = EfficiencySummary()
    if total_phases > 0:
        summary.completion_date_record_rate = dated_phases / total_phases
    summary.total_phases = total_phases
    summary.dated_phases = dated_phases
    summary.active_projects_dedup = len(active_projects_set)

    # 岗位负荷分布（项目数）
    role_load = {role: len(projects) for role, projects in role_project_count.items()}

    # 完成率 Top（按环节 phase_type 聚合按期完成率，非人维度——防火墙同源）
    type_stats: dict[str, dict] = {}  # phase_type → {name, on_time, with_date, total}
    for ph in valid_phases:
        if ph.status != "已完成":
            continue
        pt = ph.phase_type or "未知"
        if pt not in type_stats:
            type_stats[pt] = {"name": ph.name, "on_time": 0, "with_date": 0, "total": 0}
        type_stats[pt]["total"] += 1
        if ph.actual_end is not None:
            type_stats[pt]["with_date"] += 1
            if ph.plan_end is not None and ph.actual_end <= ph.plan_end:
                type_stats[pt]["on_time"] += 1
    rework_top = []
    for pt, st in type_stats.items():
        if st["with_date"] > 0:
            rework_top.append({
                "phase_type": pt,
                "name": st["name"],
                "on_time_rate": st["on_time"] / st["with_date"],
                "on_time_sample": f"{st['on_time']}/{st['with_date']}",
            })
    rework_top.sort(key=lambda x: -(x["on_time_rate"] or 0))
    rework_top = rework_top[:10]

    return TeamEfficiency(
        window_days=window_days,
        summary=summary,
        persons=persons,
        role_load=role_load,
        rework_top=rework_top,
    )
