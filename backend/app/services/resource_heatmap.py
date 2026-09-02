"""资源负载热力矩阵计算（RESOURCE_HEATMAP §2.2）。

纯函数，不写库：人员 × 时间桶矩阵，格值 = 该人员该周期相交的活跃阶段数。

规则要点（设计 v1.2 + 评审处置）：
- 过滤：phase.status not in (已完成, 已搁置) 且 project.status != 搁置
  （与 PROJECT_SHELVE §2.5 口径一致——搁置项目不占资源；旧值「已搁置」兼容已移除）
- 无任何日期（无 plan 且无 actual）不占格；仅实际日期用 actual 计入；
  半开区间（只有开始或只有结束）不占格（评审处置 #5）
- weeks 恒为窗口长度，granularity 只影响桶大小（评审处置 #8）；
  周桶周一对齐（#10），start_date 所在周含在首桶（#2）
- peak_parallel = 扫描线求窗口内任意时刻最大同时活跃数（跨桶连续，非桶内取整）
- 冲突标记复用 resource_conflicts.detect_conflicts 的冲突阶段 id 集
  （**按资源视角**，CONFLICT_MODEL_V2 §2.2：只收该人自己检测剩余对的成员阶段 id，
  共担者不连带标 ⚠；P8 三处全排除（甘特/热力图/冲突，f32717d）——不占格亦不标 ⚠）
- cell_phases[].conflict_detail：{phase_a_id, phase_b_id, partner_name,
  partner_phase_name, overlap_days}——tooltip「与谁撞」与 Drawer 消除提交一次到位
- 排序：peak_parallel 降序 → active_phases 降序；零负载入 idle_people（按名称，#11）
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Phase, Project, Resource
from app.services.resource_conflicts import detect_conflicts

# 阶段级跳过状态（与 resource_conflicts._SKIP_STATUSES 一致；独立定义避免隐式耦合）
_SKIP_PHASE_STATUSES = ("已完成", "已搁置")
# 项目级搁置状态（PROJECT_SHELVE 决策 #4；旧值「已搁置」兼容已移除——2026-08-28）
_SHELVED_PROJECT_STATUSES = ("搁置",)


def active_heatmap_phases(resource: Resource) -> list[Phase]:
    """该人员参与、且在热力图中占格的阶段（状态/项目/日期均有效）。

    日期规则：优先 plan_start/plan_end；无任何计划日期且有完整 actual 时用 actual；
    无任何日期或半开区间（只有一头）一律不占格。
    """
    result: list[Phase] = []
    for ph in resource.phases:
        if ph.status in _SKIP_PHASE_STATUSES:
            continue
        if ph.project is not None and ph.project.status in _SHELVED_PROJECT_STATUSES:
            continue
        # 专项项目：独立监控对象，不占资源负载（SPECIAL_PROJECT §二）
        if ph.project is not None and ph.project.is_special:
            continue
        # P8/P9 交付族：资源负载不计入（用户 2026-08-28：占空间且不计入负载，无存在必要；
        # PHASE_TYPES_V2 §四：旧 P8 交付 + 新 P9 交付排除，新 P8 联调测试一并排除——机制双兼容）
        if (ph.phase_type or "").upper() in ("P8", "P9"):
            continue
        if ph.plan_start is not None and ph.plan_end is not None:
            result.append(ph)  # 完整计划日期
        elif (ph.plan_start, ph.plan_end) == (None, None) and (
            ph.actual_start is not None and ph.actual_end is not None
        ):
            result.append(ph)  # 无计划但有完整实际日期 → 用 actual 计入
        # 其余（半开区间 / 完全无日期）不占格
    return result


def phase_dates(ph: Phase) -> tuple[date, date]:
    """阶段占格区间：完整计划日期优先，否则完整实际日期（entry 保证二者其一完整）。"""
    if ph.plan_start is not None and ph.plan_end is not None:
        return ph.plan_start, ph.plan_end
    return ph.actual_start, ph.actual_end  # type: ignore[return-value]


@dataclass(frozen=True)
class _Bucket:
    """一个时间桶（列）：[start, end] 双闭区间，label 为起始日。"""
    start: date
    end: date
    label: str


def _week_start(d: date) -> date:
    """d 所在周的周一（周桶对齐规则，评审处置 #10）。"""
    return d - timedelta(days=d.weekday())


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _build_buckets(window_start: date, window_end: date, granularity: str) -> list[_Bucket]:
    """窗口内切桶：week=周一对齐；month=自然月；边界桶只保留窗口内部分。"""
    buckets: list[_Bucket] = []
    if granularity == "month":
        cur = _month_start(window_start)
        while cur <= window_end:
            b_end = min(_month_end(cur), window_end)
            buckets.append(_Bucket(max(cur, window_start), b_end, cur.isoformat()))
            cur = (_month_start(cur) + timedelta(days=31)).replace(day=1)
    else:
        cur = _week_start(window_start)
        while cur <= window_end:
            b_end = min(cur + timedelta(days=6), window_end)
            buckets.append(_Bucket(max(cur, window_start), b_end, cur.isoformat()))
            cur += timedelta(days=7)
    return buckets


def _peak_parallel(intervals: list[tuple[date, date]]) -> int:
    """扫描线：窗口内任意时刻的最大同时活跃数。

    闭区间端点：start 记 +1、end 记 -1 且 end 事件先处理——
    背靠背（前一 end == 后一 start）不并行。注意与热力格口径的既定偏差：
    格按"周期与桶相交"计数（背靠背同桶会显示 2），峰值按端点事件（记 1）。
    """
    events: list[tuple[date, int]] = []
    for s, e in intervals:
        events.append((s, 1))
        events.append((e, -1))
    # 同日：-1 先于 +1（避免把背靠背交接日算成并行）
    events.sort(key=lambda ev: (ev[0], ev[1]))
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def _phase_entry(ph: Phase, project: Project, in_conflict: bool,
                 conflict_details: list[dict] | None = None) -> dict:
    s, e = phase_dates(ph)
    return {
        "phase_id": ph.id,
        "project_id": ph.project_id,
        "project_name": project.name,
        "phase_name": ph.name,
        "start": s.isoformat(),
        "end": e.isoformat(),
        "status": ph.status,
        "conflict": in_conflict,
        # CONFLICT_MODEL_V2 评审处置 #2：冲突对详情数组（该阶段该人员的全部对，
        # 用户问题 1：Drawer 每对一行独立消除）；无冲突为空数组
        "conflict_details": conflict_details or [],
    }


def _conflict_details_by_resource(db: Session) -> dict[int, dict[int, list[dict]]]:
    """按资源视角的冲突详情：{resource_id: {phase_id: [detail, ...]}}。

    仅收**该人自己** detect_conflicts 剩余对的成员阶段 id（CONFLICT_MODEL_V2 §2.2：
    共担者不连带标 ⚠）。一个阶段可能涉及多个冲突对——**全部保留**（按重叠天数
    降序），前端 Drawer 每对一行独立消除（用户问题 1：消除一对不影响其余对）。
    """
    result: dict[int, dict[int, list[dict]]] = {}
    for rc in detect_conflicts(db):
        by_phase = result.setdefault(rc.resource_id, {})
        for pair in rc.conflicts:
            for me_id, partner_phase, partner_project in (
                (pair.phase_a_id, pair.phase_b_name, pair.project_b_name),
                (pair.phase_b_id, pair.phase_a_name, pair.project_a_name),
            ):
                detail = {
                    "phase_a_id": min(pair.phase_a_id, pair.phase_b_id),
                    "phase_b_id": max(pair.phase_a_id, pair.phase_b_id),
                    "partner_name": partner_project,
                    "partner_phase_name": partner_phase,
                    "overlap_days": pair.overlap_days,
                    # 消除影响范围提示（用户问题 1）：该重叠覆盖的起止日期
                    "overlap_start": pair.overlap_start.isoformat(),
                    "overlap_end": pair.overlap_end.isoformat(),
                }
                by_phase.setdefault(me_id, []).append(detail)
        for lst in by_phase.values():
            lst.sort(key=lambda d: d["overlap_days"], reverse=True)
    return result


def build_heatmap(db: Session, weeks: int = 12, granularity: str = "week") -> dict:
    """构建热力矩阵（RESOURCE_HEATMAP §2.1 响应结构）。

    weeks: 窗口长度（周数），weeks>0 → 起点 N-1 周前的周一；右端=今天+8 周
           （月视图=第 3 个整月月末）——未来计划负载固定可见（2026-08-29 需求）；
           0=全部（最早数据日期 → 最晚计划，含未来）
    granularity: 'week' | 'month'（桶大小；影响窗口右端的未来延展口径）
    """
    today = date.today()
    latest_plan = db.scalar(select(func.max(Phase.plan_end)))
    latest_actual = db.scalar(select(func.max(Phase.actual_end)))

    # ---------- 窗口 ----------
    if weeks > 0:
        # weeks>0（裁决 A + 2026-08-29 需求）：起点 = N-1 周前的周一；右端延至未来——
        # 周视图 = 今天 + 8 周（未来计划负载在固定窗口内直接可见）；
        # 月视图 = 今天所在月起 + 3 个整月（自然月对齐，右端 = 第 3 个月月末）。
        # （历史注：裁决 A 原为右端=今天，2026-08-29 用户需求改为含未来 8 周/3 个月）
        if granularity == "month":
            # 月视图起点 = 今天所在月首（不经过周对齐——否则月初后半月会多出上一月桶）
            month_anchor = _month_start(today)
            window_start = month_anchor
            window_end = _month_end(_month_start(month_anchor + timedelta(days=92)))
        else:
            window_end = today + timedelta(weeks=8)
            window_start = _week_start(today - timedelta(weeks=weeks - 1))
    else:
        # 0=全部：右端 = max(today, 最晚计划)——未来计划负载必须可见（含未来）；
        # 起点 = 全部人员有效阶段的最早日期（无任何数据 → 仅本周）
        window_end = max(today, latest_plan or today, latest_actual or today)
        earliest: date | None = None
        for res in db.scalars(select(Resource)):
            for ph in active_heatmap_phases(res):
                s, _ = phase_dates(ph)
                if earliest is None or s < earliest:
                    earliest = s
        window_start = _week_start(earliest) if earliest else _week_start(today)
        if granularity == "month":
            window_start = _month_start(window_start)

    buckets = _build_buckets(window_start, window_end, granularity)
    columns = [b.label for b in buckets]

    # ---------- 冲突标记（按资源视角，CONFLICT_MODEL_V2 §2.2） ----------
    conflict_details = _conflict_details_by_resource(db)

    # ---------- 每人一行 ----------
    people: list[dict] = []
    idle: list[dict] = []
    for res in db.scalars(select(Resource).order_by(Resource.id)):
        # 仅统计与窗口相交的阶段（peak/active 都是"窗口内"口径，设计 §2.2）。
        # 用户 2026-08-28：消除冲突仅抑制警告，热力图仍显示实际并行数——不剔除 override 阶段
        phases = [
            ph for ph in active_heatmap_phases(res)
            if phase_dates(ph)[0] <= window_end and phase_dates(ph)[1] >= window_start
        ]
        intervals = [phase_dates(ph) for ph in phases]

        # 该人的冲突详情（仅为本人检测剩余对的成员标 ⚠；P8 阶段不在冲突集 → 不标）
        res_conflicts = conflict_details.get(res.id, {})

        cells = [0] * len(buckets)
        cell_entries: list[list[dict]] = [[] for _ in buckets]
        for ph, (ps, pe) in zip(phases, intervals):
            ph_entry: dict | None = None  # 惰性构建（仅首个相交桶需要）
            for idx, b in enumerate(buckets):
                if ps <= b.end and pe >= b.start:  # 与桶相交 → 计入
                    cells[idx] += 1
                    if ph_entry is None:
                        details = res_conflicts.get(ph.id)
                        ph_entry = _phase_entry(ph, ph.project, bool(details), details)
                    cell_entries[idx].append(dict(ph_entry))

        if not any(cells):
            idle.append({
                "resource_id": res.id,
                "name": res.name,
                "role": res.role,
            })
            continue

        people.append({
            "resource_id": res.id,
            "name": res.name,
            "role": res.role,
            "peak_parallel": _peak_parallel(intervals),
            "active_phases": len(phases),
            "cells": cells,
            "cell_phases": [entries or None for entries in cell_entries],
        })

    people.sort(key=lambda p: (-p["peak_parallel"], -p["active_phases"]))
    idle.sort(key=lambda p: p["name"])  # 评审处置 #11

    return {
        "start_date": window_start.isoformat(),
        "end_date": window_end.isoformat(),
        "granularity": granularity,
        "columns": columns,
        "people": people,
        "idle_people": idle,
    }
