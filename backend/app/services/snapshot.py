"""每日状态快照服务（PROJECT_ANALYSIS §3.2）。

- collect_metrics：= build_dashboard_stats（看板同口径单一来源）+ §二扩展指标
- create_today_if_absent：幂等建行——当日已有即跳过（唯一约束兜底并发）
- build_trend：日级点位 + 周级聚合（周一锚点），差分在查询时算
- 8-3 项目级（PHASE8_PLAN §三）：collect_project_metrics（四键定格）+
  snapshot_projects_today（只拍在办，upsert 幂等）+ build_project_trend（混合粒度读）+
  build_project_events（延期/冲突/计划变更三类事件点）

快照只存原子计数；比率/差分均由查询侧计算，未来加图不改历史快照结构。
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DataChangeEvent, Phase, Project, ProjectSnapshot, StatusSnapshot
# 函数内导入：snapshot.py 顶部 import routers.dashboard（build_dashboard_stats 看板同源口径），
# routers/__init__ 会级联拉起 projects.py，而 projects.py 顶部又 import 本模块的 build_project_* ——
# 顶层互引成循环导入，CLI 入口（python -m app.jobs.snapshot，生产 crontab）直接 ImportError。
# 与 routers/dashboard.py:294 的既有同款处理（函数内导入）保持一致。
from app.services.change_events import FIELD_LABELS
from app.services.resource_conflicts import detect_conflicts
from app.services.resource_heatmap import build_heatmap

# 未完成阶段口径（阶段级未结束状态；与 dashboard 延期判定同族）
_OPEN_PHASE_EXCLUDED_STATUSES = ("已完成", "搁置")
# 周差分指标键：累计量差分有吞吐含义（每周完成项目数 / 每周转搁置 / 每周新开工 —— 均项目级，用户 2026-10-26 裁定：统计聚焦项目级）；
# 延期阶段数/冲突对数为存量型差分（8-1 看板环比与趋势差分用，2026-11-04 批次裁定：随 build_trend 周差分同源输出）
_WEEKLY_DELTA_KEYS = (
    "completed_projects_total",
    "shelved_total",
    "started_projects_total",
    "delayed_phases",
    "conflict_pairs",
)
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
    # 函数内导入（循环导入——见本文件头部 import 注释）
    from app.routers.dashboard import build_dashboard_stats

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
        "active_projects": stats.active_projects,  # 进行中项目数（看板「进行中」卡环比）
        "total_rework_count": stats.total_rework_count,  # 返工总次数（看板「返工次数」卡环比）
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
    delta 仅对 _WEEKLY_DELTA_KEYS 键做相邻周差分（周内最后快照相减，周一锚点），首周为 0。
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


def build_weekly_delta(db: Session, keys: Sequence[str], days: int = 30) -> dict[str, int | None] | None:
    """看板环比取数（8-1）：最新周点与上一周点的 metrics 相减（与 build_trend 周差分同一公式、同一快照源）。

    任意指标键均按公式现算；任一侧周点缺键 → 该键视为不可比，输出 None（不用 0 冒充「无变化」，与下方周点不足的同源原则）。
    """
    rows = db.scalars(select(StatusSnapshot).order_by(StatusSnapshot.snapshot_date)).all()
    weekly = build_trend(rows, days=days)["weekly"]
    if len(weekly) < 2:
        return None
    cur, prev = weekly[-1]["metrics"], weekly[-2]["metrics"]
    delta = {k: cur.get(k, 0) - prev.get(k, 0) for k in keys}
    # 任一侧周点缺键（如历史快照早于指标接入）→ 该键环比不可知，置 None 不冒充 0
    for k in keys:
        if k not in cur or k not in prev:
            delta[k] = None
    return delta


# ============================================================
# 8-3 项目级快照（PHASE8_PLAN §三 方案 A + 口径③；批次档 项目趋势-2026-11-10 §2）
# ============================================================

# 项目级快照 metrics 四键（均为快照时点定格值——读时不重算，计划改动不扭曲历史）
_PROJECT_METRIC_KEYS = ("plan_cum_pct", "actual_cum_pct", "delayed_phases", "conflict_pairs")
# 项目级快照采集的粒度标记键（降采样后行带 day/week/month；采集侧写日行）
_GRANULARITY_KEY = "_granularity"


def collect_project_metrics(
    db: Session,
    project: Project,
    today: date | None = None,
    conflicts: Sequence | None = None,
) -> dict:
    """采集单项目快照 metrics（时点值，随快照定格）。

    四键口径（与看板同源，§3.5 验收①「当日末点与看板当日数字一致」）：
    - plan_cum_pct：计划累计完成度 = 按快照当日阶段计划排期算——已完成阶段（按计划应在
      当日或更早收尾）数 ÷ 总阶段数 ×100。按「计划进度」计而非实际进度，计划曲线随快照定格。
    - actual_cum_pct：实际累计完成度 = 已完成阶段（actual_end ≤ 当日，未填 actual_end 的
      已完成阶段按当日完成计）÷ 总阶段数 ×100；无阶段 → None（缺数据不冒充 0，§3.5 口径）。
    - delayed_phases：延期阶段数 = plan_end < 当日 且状态 ∉ {已完成, 搁置}——
      与 dashboard 延期判定同族（本文件 _OPEN_PHASE_EXCLUDED_STATUSES 同口径），排除专项由调用方保证。
    - conflict_pairs：该项目涉入的资源冲突对数（detect_conflicts 同源检测）。

    conflicts：调用方可传入已算好的 detect_conflicts 结果（批量采集时避免逐项目全库重扫）；
    缺省 None = 函数内自行检测（单项目调用路径）。
    """
    today = today or date.today()
    phases = list(project.phases)
    total = len(phases)
    if total == 0:
        return {k: None for k in _PROJECT_METRIC_KEYS}

    # 计划累计完成度：按计划排期应已完成的阶段占比（计划当日收尾即计入——「应完成」口径）
    plan_done = sum(
        1 for ph in phases
        if ph.plan_end is not None and ph.plan_end <= today and ph.status not in ("搁置",)
    )
    # 实际累计完成度：已完成阶段占比（actual_end ≤ 当日；未填完成日的已完成阶段按当日完成计）
    actual_done = sum(
        1 for ph in phases
        if ph.status == "已完成" and (ph.actual_end is None or ph.actual_end <= today)
    )

    delayed = sum(
        1 for ph in phases
        if ph.plan_end is not None
        and ph.plan_end < today
        and ph.status not in ("已完成", "搁置")
    )

    # 该项目涉入的冲突对数：detect_conflicts 同源检测（与看板/8-2 同源；批量路径由调用方
    # 传入已算好的 conflicts 避免逐项目全库重扫）
    if conflicts is None:
        conflicts = detect_conflicts(db)
    pair_count = 0
    for rc in conflicts:
        for pair in rc.conflicts:
            if project.id in (pair.project_a_id, pair.project_b_id):
                pair_count += 1

    return {
        "plan_cum_pct": round(plan_done / total * 100),
        "actual_cum_pct": round(actual_done / total * 100),
        "delayed_phases": delayed,
        "conflict_pairs": pair_count,
    }


def snapshot_projects_today(db: Session, today: date | None = None) -> tuple[int, int]:
    """项目级采集主入口：只拍在办项目（状态 ∈ {未开始, 进行中}，专项排除）。

    幂等：同日已有行 → 重新采集覆盖（upsert 语义，同 create_today_if_absent force 模式）——
    crontab 重跑/手动触发不产生两行（唯一约束 (project_id, snapshot_date) 兜底并发）。

    返回 (采集项目数, 新建行数)——覆盖已有行不计入新建（与全局快照 created 语义对齐）。
    """
    today = today or date.today()
    in_flight = db.scalars(
        select(Project).where(
            Project.status.in_(_IN_FLIGHT_STATUSES),
            Project.is_special.is_(False),
        )
    ).all()

    # 冲突检测一次全库跑（评审 #4：循环内逐项目调 detect_conflicts 是 N 次全库扫描——
    # 冲突关系在一次采集运行内不变，提出循环外算一次、逐项目过滤）
    conflicts = detect_conflicts(db)

    created_count = 0
    for project in in_flight:
        existing = db.scalar(
            select(ProjectSnapshot).where(
                ProjectSnapshot.project_id == project.id,
                ProjectSnapshot.snapshot_date == today,
            )
        )
        metrics = collect_project_metrics(db, project, today, conflicts=conflicts)
        metrics[_GRANULARITY_KEY] = "day"
        if existing is not None:
            existing.metrics = metrics  # 同日重触发：覆盖当日行，不新增
            continue
        db.add(ProjectSnapshot(
            project_id=project.id,
            snapshot_date=today,
            metrics=metrics,
            project_code=project.code,
            project_name=project.name,
        ))
        try:
            db.flush()
            created_count += 1
        except IntegrityError:
            # 并发兜底（另一进程先建行）：回滚后重查、按幂等覆盖语义处理——本函数为每日
            # 批量采集（单行 flush 无跨行事务依赖），db.rollback() 只丢当前冲突行；
            # 若未来引入跨行事务（如同轮多行原子提交），此处须改 SAVEPOINT（begin_nested）。
            db.rollback()
            existing = db.scalar(
                select(ProjectSnapshot).where(
                    ProjectSnapshot.project_id == project.id,
                    ProjectSnapshot.snapshot_date == today,
                )
            )
            if existing is None:
                raise  # 约束冲突却查不到行——异常状态显式抛出，不做静默兜底
            existing.metrics = metrics
            db.commit()
    return len(in_flight), created_count


def build_project_trend(
    rows: Sequence[ProjectSnapshot],
    days: int,
    today: date | None = None,
) -> list[dict]:
    """项目趋势混合点列（分层降采样读口径）。

    行已带粒度标记（metrics._granularity：day/week/month）；窗口内行按日期升序统一透出，
    缺失日期断开不补零（§3.5 验收②——列表只含真实快照日）。
    降采样维护（maintain_project_snapshots）由 PG 侧函数执行；此处纯读。
    """
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    points: list[dict] = []
    for r in sorted(rows, key=lambda x: x.snapshot_date):
        if not (start <= r.snapshot_date <= today):
            continue
        metrics = dict(r.metrics or {})
        granularity = metrics.pop(_GRANULARITY_KEY, "day")
        points.append({
            "date": r.snapshot_date.isoformat(),
            "granularity": granularity,
            "metrics": {k: metrics.get(k) for k in _PROJECT_METRIC_KEYS},
        })
    return points


def build_project_events(
    db: Session,
    *,
    project_id: int | None,
    project_code: str | None,
    days: int,
    snapshots: Sequence[ProjectSnapshot],
    today: date | None = None,
) -> list[dict]:
    """三类事件点（P2 数据通道，批次档 §2 设计点 4）。

    - 延期/冲突：取自快照 metrics（>0 的快照日即事件日——数据源「与看板同源计数」）
    - 计划变更：data_change_events field ∈ {plan_start, plan_end}（项目级白名单字段名），
      按 created_at 对齐时间轴；被删项目（project_id SET NULL）按 project_name 冗余字段匹配。
    """
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    events: list[dict] = []

    for r in snapshots:
        if not (start <= r.snapshot_date <= today):
            continue
        m = r.metrics or {}
        if m.get("delayed_phases"):
            events.append({
                "date": r.snapshot_date.isoformat(),
                "kind": "delayed",
                "detail": f"{m['delayed_phases']} 个阶段延期",
            })
        if m.get("conflict_pairs"):
            events.append({
                "date": r.snapshot_date.isoformat(),
                "kind": "conflict",
                "detail": f"{m['conflict_pairs']} 对资源冲突",
            })

    # 计划变更事件：field ∈ {plan_start, plan_end}（FIELD_LABELS 里项目级计划时间两字段）
    plan_fields = ("plan_start", "plan_end")
    if project_id is not None:
        cond = DataChangeEvent.project_id == project_id
    else:
        # 被删项目：project_id 已 SET NULL，按冗余 project_name 匹配（同一项目名的其他行也可能命中，
        # 但事件行 project_name 冗余的是事件时点项目名——与快照最后一次名字口径一致）
        cond = DataChangeEvent.project_name == project_code  # 兜底：编号误存 name 时也可寻址
        cond = cond | (DataChangeEvent.project_name == (
            db.scalar(
                select(ProjectSnapshot.project_name)
                .where(ProjectSnapshot.project_code == project_code)
                .order_by(ProjectSnapshot.snapshot_date.desc())
                .limit(1)
            )
        ))
    field_cond = DataChangeEvent.field.in_(plan_fields)
    time_cond = DataChangeEvent.created_at >= datetime.combine(start, time.min)
    event_rows = db.scalars(
        select(DataChangeEvent).where(cond, field_cond, time_cond).order_by(DataChangeEvent.created_at)
    ).all()
    for e in event_rows:
        label = FIELD_LABELS.get(e.field, e.field)
        old_v = e.old_value if e.old_value is not None else "（空）"
        new_v = e.new_value if e.new_value is not None else "（空）"
        who = e.changed_by_name or "（已注销）"
        events.append({
            "date": e.created_at.date().isoformat(),
            "kind": "plan_change",
            "detail": f"{label} {old_v} → {new_v}（{who}）",
        })
    return events
