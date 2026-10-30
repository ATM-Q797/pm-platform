"""每日状态快照服务（PROJECT_ANALYSIS §3.2）。

- collect_metrics：= build_dashboard_stats（看板同口径单一来源）+ §二扩展指标
- create_today_if_absent：幂等建行——当日已有即跳过（唯一约束兜底并发）
- build_trend：日级点位 + 周级聚合（周一锚点），差分在查询时算

快照只存原子计数；比率/差分均由查询侧计算，未来加图不改历史快照结构。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Phase, Project, StatusSnapshot
from app.routers.dashboard import build_dashboard_stats
from app.services.resource_heatmap import build_heatmap

# 未完成阶段口径（阶段级未结束状态；与 dashboard 延期判定同族）
_OPEN_PHASE_EXCLUDED_STATUSES = ("已完成", "搁置")
# 周差分指标键：仅累计量差分有吞吐含义（每周完成项目数 / 每周转搁置 / 每周新开工 —— 均项目级，用户 2026-10-26 裁定：统计聚焦项目级）
_WEEKLY_DELTA_KEYS = ("completed_projects_total", "shelved_total", "started_projects_total")
# 在期项目状态（用户 2026-10-26 确认：未开始 + 进行中）
_IN_FLIGHT_STATUSES = ("未开始", "进行中")
# 计划工期异常阈值（沿工期异常清单口径，用户 2026-10-26 确认：>120 天超长、<7 天过短）
_PLAN_DAYS_TOO_LONG = 120
_PLAN_DAYS_TOO_SHORT = 7


def _percentile(sorted_values: list[int], q: float) -> int:
    """线性插值分位数（输入须升序）；空集返回 0（无延期时深度为 0）。"""
    if not sorted_values:
        return 0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * q
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_values[lo]
    return round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo))


def collect_metrics(db: Session) -> dict:
    """采集当日指标（原子计数）。

    专项项目不纳入任何统计（用户裁定 2026-10-26）：
    - 看板部分（build_dashboard_stats）本就排除专项
    - 扩展指标（open/completed/shelved）查询显式排除 is_special
    - 冲突/热力图口径由 resource 服务内含排除（resource_conflicts/resource_heatmap）
    """
    stats = build_dashboard_stats(db)

    # 热力图口径（resource_heatmap 已排除专项/搁置/交付族）：
    # 活跃人员 = 窗口内有负载的人数；top3 均值 = 峰值并行前 3 人均值（people 已按峰值降序）
    heatmap = build_heatmap(db, weeks=12, granularity="week")
    people = heatmap["people"]
    top3 = [p["peak_parallel"] for p in people[:3]]

    open_phases = db.scalar(
        select(func.count())
        .select_from(Phase)
        .join(Project, Phase.project_id == Project.id)
        .where(
            ~Phase.status.in_(_OPEN_PHASE_EXCLUDED_STATUSES),
            Project.is_special.is_(False),
        )
    ) or 0
    completed_total = db.scalar(
        select(func.count())
        .select_from(Phase)
        .join(Project, Phase.project_id == Project.id)
        .where(
            Phase.status == "已完成",
            Project.is_special.is_(False),
        )
    ) or 0
    shelved_total = next(
        (sc.count for sc in stats.project_status if sc.status == "搁置"), 0
    )

    overdue_days = sorted(p.overdue_days for p in stats.delayed_phases)

    # ---- 项目级扩展指标（用户 2026-10-26 四板块裁定，全部排除专项）----
    today = date.today()

    # 在期项目 = 状态 ∈ {未开始, 进行中}（用户确认口径）
    in_flight = next(
        (sc.count for s in _IN_FLIGHT_STATUSES for sc in stats.project_status if sc.status == s), 0
    )

    # 7 天内到期项目数（项目级预警，口径对齐 dashboard due_soon：项目整体 plan_end ∈ [today, today+7]
    # 且状态未完成未搁置；区别于阶段级 due_soon_phases）
    due_soon_projects = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.plan_end >= today,
                Project.plan_end <= today + timedelta(days=7),
                Project.status.in_(_IN_FLIGHT_STATUSES),
                Project.is_special.is_(False),
            )
        )
        or 0
    )

    # 计划工期异常项目数（工期异常清单同款阈值：计划工期 > 120 天超长 / < 7 天过短；
    # 两头日期齐全才可判，未完成状态项目全部纳入——异常清单口径即含已完成项目）
    plan_days_rows = db.execute(
        select(Project.plan_start, Project.plan_end)
        .where(
            Project.plan_start.is_not(None),
            Project.plan_end.is_not(None),
            Project.is_special.is_(False),
        )
    ).all()
    plan_days_too_long = 0
    plan_days_too_short = 0
    for ps, pe in plan_days_rows:
        days = (pe - ps).days
        if days > _PLAN_DAYS_TOO_LONG:
            plan_days_too_long += 1
        elif days < _PLAN_DAYS_TOO_SHORT:
            plan_days_too_short += 1

    # 项目级吞吐累计量（周差分基期）：累计完成项目数 / 累计转搁置数 / 累计新开工项目数。
    # 新开工 = plan_start 已到（<= today）且状态 ∈ {未开始, 进行中, 已完成}（未履约完成过的启动口径——
    # created_at 全库为导入时间不可用，用计划开始日作代理，工单口径在图题注明）
    completed_projects = next((sc.count for sc in stats.project_status if sc.status == "已完成"), 0)
    started_projects = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.plan_start <= today,
                Project.status.in_(("未开始", "进行中", "已完成")),
                Project.is_special.is_(False),
            )
        )
        or 0
    )

    # 市场/类目分布（最新盘面用，快照日原子计数；仅非专项）
    by_market_rows = db.execute(
        select(Project.market, func.count())
        .where(Project.is_special.is_(False))
        .group_by(Project.market)
    ).all()
    by_category_rows = db.execute(
        select(Project.category, func.count())
        .where(Project.is_special.is_(False))
        .group_by(Project.category)
    ).all()

    return {
        "projects_total": stats.total_projects,
        "projects_by_status": {sc.status: sc.count for sc in stats.project_status},
        "delayed_projects": stats.delayed_count,
        "delayed_phases": len(stats.delayed_phases),
        "delayed_days_p50": _percentile(overdue_days, 0.5),
        "delayed_days_p90": _percentile(overdue_days, 0.9),
        "due_soon_phases": stats.due_soon_count,
        "conflict_pairs": stats.conflict_count,
        "active_people": len(people),
        "peak_parallel_top3_avg": round(sum(top3) / len(top3), 1) if top3 else 0,
        "open_phases": open_phases,
        "completed_phases_total": completed_total,
        "shelved_total": shelved_total,
        # ---- 项目级扩展（四板块）----
        "in_flight_projects": in_flight,
        "due_soon_projects": due_soon_projects,
        "plan_days_too_long": plan_days_too_long,
        "plan_days_too_short": plan_days_too_short,
        "started_projects_total": started_projects,
        "completed_projects_total": completed_projects,
        "projects_by_market": {m: c for m, c in by_market_rows},
        "projects_by_category": {c: n for c, n in by_category_rows},
    }


def create_today_if_absent(db: Session, force: bool = False) -> tuple[StatusSnapshot, bool]:
    """幂等创建当日快照：当日已有 → 原样返回 (existing, False)；否则采集并建行 (row, True)。

    force=True（用户 2026-10-29 指令：分析弹窗"数据刷新"按钮）：当日已有也重新采集覆盖，
    让导入新项目表后可立即看到最新分析；快照历史仍保持每日一行（覆盖当日，不新增行）。

    并发兜底：两个 worker 同时越过存在性检查时，snapshot_date 唯一约束让
    第二个 commit 失败 → 回滚重查（多 worker 下重复触发不产生两行）。
    """
    today = date.today()
    existing = db.scalar(select(StatusSnapshot).where(StatusSnapshot.snapshot_date == today))
    if existing is not None and not force:
        return existing, False
    if existing is not None:
        existing.metrics = collect_metrics(db)
        db.commit()
        db.refresh(existing)
        return existing, True
    snapshot = StatusSnapshot(snapshot_date=today, metrics=collect_metrics(db))
    db.add(snapshot)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(StatusSnapshot).where(StatusSnapshot.snapshot_date == today))
        if existing is None:
            raise  # 约束冲突却查不到行——异常状态显式抛出，不做静默兜底
        return existing, False
    db.refresh(snapshot)
    return snapshot, True


def build_trend(rows: Sequence[StatusSnapshot], days: int, today: date | None = None) -> dict:
    """构建趋势数据：days 窗口内的日级点位 + 周级聚合（周一锚点）。

    rows 须按 snapshot_date 升序。周点 metrics = 周内最后一个快照；
    delta 仅对累计量键（_WEEKLY_DELTA_KEYS）做相邻周差分，首周为 0。
    """
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    daily = [
        {"date": r.snapshot_date.isoformat(), "metrics": r.metrics}
        for r in rows
        if start <= r.snapshot_date <= today
    ]

    # 周聚合：升序遍历同周覆盖 → 保留周内最后一个快照
    weeks: dict[date, dict] = {}
    order: list[date] = []
    for point in daily:
        d = date.fromisoformat(point["date"])
        week_start = d - timedelta(days=d.weekday())
        if week_start not in weeks:
            order.append(week_start)
        weeks[week_start] = point

    weekly: list[dict] = []
    prev: dict | None = None
    for week_start in order:
        metrics = weeks[week_start]["metrics"]
        if prev is None:
            delta = {k: 0 for k in _WEEKLY_DELTA_KEYS}
        else:
            delta = {k: metrics.get(k, 0) - prev.get(k, 0) for k in _WEEKLY_DELTA_KEYS}
        weekly.append({
            "week_start": week_start.isoformat(),
            "metrics": metrics,
            "delta": delta,
        })
        prev = metrics

    return {"days": days, "daily": daily, "weekly": weekly}
