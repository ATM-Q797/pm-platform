"""过程事件审计分析服务（P3，PHASE8_PLAN §九 三指标）。

三指标聚合（纯读不写，列名锚定真表，批档 §2 一）：
- 计划稳定性（项目粒度）：窗口内白名单计划字段变更事件次数 + 累计挪动天数 Σ|new−old|
  （按字段变更事件计次计天——一次编辑同改两字段 = 2 次、整体平移按字段各计）。
- 估算偏差（阶段粒度）：首次计划工期 vs 实际工期/交付偏差；
  配对规则 = 按字段独立取首值再成对（该字段有事件取其最早事件 old_value；无事件取 phase 对应列现值——未改过即首次）。
- 审批时效（全局/市场粒度）：phase_change_request「提交(created_at)→决于(reviewed_at)」
  （「批下来」按「决于」读，含驳回件；仅 approved 均值可切换）。
  source=approval 事件只作条数对照，不参与时效计算（事件表无提交时刻）。

口径边界：
- 值解析按 YYYY-MM-DD；解析失败计入 move_parse_skipped 显式返回，不静默丢弃、不计天数
  （分支出处：日期首次设置/清空事件的 old_value 或 new_value 为空、非日期字面 → 解析失败入 skipped）。
- 首值缺失（old_value 为空——阶段日期为空时首次设置无旧值）成对不可用 → 该阶段归 first_plan_skipped
  显式计数、不计入明细（在案观察：PHASE8_PLAN「N 个活跃阶段无计划日期，未纳入判定」）。
- 仅统计 actual_end 非空阶段（在途不计，口径不可比）；审批 pending 不计。
- 历史不回填：data_start 取 data_change_events 首事件日（动态取，不硬编码日期字面）。
- 窗口 = [今天−days, 今天] 日历日窗（与 30/90/365 三档同款）；created_at/reviewed_at 按时间戳、
  actual_end 按日期对窗。

防火墙（§9.3「不做绩效评分/排名」）：返回体不设按人（changed_by）聚合维度——直接落实为无维度。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import DataChangeEvent, PhaseChangeRequest
from app.models.phase import Phase
from app.models.project import Project

# 白名单计划字段（change_events.FIELD_LABELS 守门）：项目级 + 阶段级
PLAN_FIELDS_PROJECT = ("plan_start", "plan_end")
PLAN_FIELDS_PHASE = ("phase_plan_start", "phase_plan_end")
PLAN_FIELDS = PLAN_FIELDS_PROJECT + PLAN_FIELDS_PHASE

# 已决状态（「决于」= reviewed_at 非空且 status 终态）；pending 不计
_DECIDED_STATUSES = ("approved", "rejected")


def _parse_date(value: str | None) -> date | None:
    """按 YYYY-MM-DD 严格解析；空/非日期字面 → None（解析失败，不猜格式）。"""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _plan_stability(
    events: list[DataChangeEvent],
    project_names: dict[int, str],
    market_ids: set[int] | None,
) -> tuple[list[dict[str, Any]], int]:
    """计划稳定性项目行聚合：窗口内事件按项目分列计次计天。

    - 计次：每事件 1 次（按字段变更事件计）；项目级/阶段级分列。
    - 计天：old/new 均按 YYYY-MM-DD 解析成功才计 |new−old|；否则入 skipped（不静默丢弃、不计天数）。
    - 已删项目事件（project_id 置 NULL）按冗余 project_name 归行保留——不静默丢弃。
    """
    agg: dict[Any, dict[str, Any]] = {}
    skipped = 0
    for ev in events:
        if market_ids is not None and ev.project_id not in market_ids:
            continue  # 市场过滤锚 Project.market；已删项目市场不可考，随过滤排除
        key: Any = ev.project_id if ev.project_id is not None else ("__deleted__", ev.project_name or "")
        row = agg.get(key)
        if row is None:
            row = {
                "project_id": ev.project_id,
                "project_name": project_names.get(ev.project_id) or ev.project_name,
                "change_count_project": 0,
                "change_count_phase": 0,
                "move_days_project": 0,
                "move_days_phase": 0,
            }
            agg[key] = row
        is_project_field = ev.field in PLAN_FIELDS_PROJECT
        if is_project_field:
            row["change_count_project"] += 1
        else:
            row["change_count_phase"] += 1
        old = _parse_date(ev.old_value)
        new = _parse_date(ev.new_value)
        if old is None or new is None:
            skipped += 1
            continue
        move = abs((new - old).days)
        if is_project_field:
            row["move_days_project"] += move
        else:
            row["move_days_phase"] += move

    rows: list[dict[str, Any]] = []
    for row in agg.values():
        row["move_days_total"] = row["move_days_project"] + row["move_days_phase"]
        rows.append(row)
    # 已删项目行（project_id None）排尾；其余按 project_id 升序（可复算，稳定序）
    rows.sort(key=lambda r: (r["project_id"] is None, r["project_id"] or 0, r["project_name"] or ""))
    return rows, skipped


def _first_plan_value(
    phase_id: int,
    field: str,
    current: date | None,
    first_old: dict[tuple[int, str], str | None],
) -> date | None:
    """单字段首值（配对规则：按字段独立取首值再成对）。

    有事件 → 其最早事件 old_value（空/非日期字面 → 首值缺失 None）；
    无事件 → phase 对应列现值（未改过即首次）。
    """
    key = (phase_id, field)
    if key in first_old:
        return _parse_date(first_old[key])
    return current


def _estimation_deviation(
    db: Session,
    phase_rows: list[tuple[int, int, str, date | None, date | None, date | None, date | None]],
    project_names: dict[int, str],
) -> tuple[list[dict[str, Any]], int]:
    """估算偏差阶段行：首次计划（全事件史回溯）vs 实际；成对缺失归 first_plan_skipped。"""
    if not phase_rows:
        return [], 0
    phase_ids = [row[0] for row in phase_rows]
    # 首值回溯不受窗口限制（首次计划 = 最早事件 old_value，窗口只选阶段不选事件）
    fp_events = db.scalars(
        select(DataChangeEvent)
        .where(
            DataChangeEvent.phase_id.in_(phase_ids),
            DataChangeEvent.field.in_(PLAN_FIELDS_PHASE),
        )
        .order_by(DataChangeEvent.created_at, DataChangeEvent.id)
    ).all()
    first_old: dict[tuple[int, str], str | None] = {}
    for ev in fp_events:
        first_old.setdefault((ev.phase_id, ev.field), ev.old_value)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for ph_id, proj_id, ph_name, col_start, col_end, actual_start, actual_end in phase_rows:
        first_start = _first_plan_value(ph_id, "phase_plan_start", col_start, first_old)
        first_end = _first_plan_value(ph_id, "phase_plan_end", col_end, first_old)
        if first_start is None or first_end is None:
            skipped += 1  # 成对缺失：该阶段不计入并显式计数
            continue
        plan_duration = (first_end - first_start).days
        actual_duration = (actual_end - actual_start).days if actual_start else None
        rows.append({
            "project_id": proj_id,
            "project_name": project_names.get(proj_id),
            "phase_id": ph_id,
            "phase_name": ph_name,
            "first_plan_start": first_start.isoformat(),
            "first_plan_end": first_end.isoformat(),
            "actual_start": actual_start.isoformat() if actual_start else None,
            "actual_end": actual_end.isoformat(),
            "plan_duration_days": plan_duration,
            "actual_duration_days": actual_duration,
            "deviation_days": actual_duration - plan_duration if actual_duration is not None else None,
            "delivery_deviation_days": (actual_end - first_end).days,
        })
    return rows, skipped


def _approval_latency(reqs: list[PhaseChangeRequest]) -> dict[str, Any]:
    """审批时效：已决（approved/rejected）「提交→决于」均值；仅 approved 均值可切换。

    无样本返回 None（缺数据不冒充 0）。
    """
    hours = [(r.reviewed_at - r.created_at).total_seconds() / 3600 for r in reqs]
    approved = [h for h, r in zip(hours, reqs) if r.status == "approved"]
    return {
        "avg_hours": sum(hours) / len(hours) if hours else None,
        "count": len(hours),
        "approved_avg_hours": sum(approved) / len(approved) if approved else None,
        "approved_count": len(approved),
    }


def compute_process_audit(
    db: Session,
    *,
    days: int,
    market: str | None = None,
    project_id: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """三指标聚合入口（纯读）。返回 dict，由路由装入 ProcessAuditResult。

    参数：days 时间窗（30/90/365 三档，路由校验）；market 锚 Project.market 过滤（可选）；
    project_id 单项目明细（可选）。today 供测试注入，缺省取当天。
    """
    today = today or date.today()
    win_lo = today - timedelta(days=days)
    win_hi = today
    dt_lo = datetime.combine(win_lo, time.min)
    dt_hi = datetime.combine(win_hi + timedelta(days=1), time.min)

    # 项目名/市场：一次取全表（不做按人/按项目维度展开，只取聚合所需列）
    proj_rows = db.execute(select(Project.id, Project.name, Project.market)).all()
    project_names = {row[0]: row[1] for row in proj_rows}
    market_ids: set[int] | None = None
    if market is not None:
        market_ids = {row[0] for row in proj_rows if row[2] == market}

    # ① 计划稳定性：窗口内 4 个计划字段事件（created_at ∈ 窗口）
    ev_q = (
        select(DataChangeEvent)
        .where(
            DataChangeEvent.field.in_(PLAN_FIELDS),
            DataChangeEvent.created_at >= dt_lo,
            DataChangeEvent.created_at < dt_hi,
        )
        .order_by(DataChangeEvent.id)
    )
    if project_id is not None:
        ev_q = ev_q.where(DataChangeEvent.project_id == project_id)
    plan_rows, move_parse_skipped = _plan_stability(
        db.scalars(ev_q).all(), project_names, market_ids
    )

    # ② 估算偏差：actual_end 非空且 ∈ 窗口的阶段（在途不计）
    ph_q = (
        select(
            Phase.id, Phase.project_id, Phase.name,
            Phase.plan_start, Phase.plan_end, Phase.actual_start, Phase.actual_end,
        )
        .where(Phase.actual_end.is_not(None), Phase.actual_end >= win_lo, Phase.actual_end <= win_hi)
        .order_by(Phase.project_id, Phase.sequence, Phase.id)
    )
    if project_id is not None:
        ph_q = ph_q.where(Phase.project_id == project_id)
    phase_rows = [tuple(r) for r in db.execute(ph_q).all()]
    if market_ids is not None:
        phase_rows = [r for r in phase_rows if r[1] in market_ids]
    est_rows, first_plan_skipped = _estimation_deviation(db, phase_rows, project_names)

    # ③ 审批时效：已决行 reviewed_at ∈ 窗口（pending 不计；source=approval 事件不参与计算）
    req_q = select(PhaseChangeRequest).where(
        PhaseChangeRequest.status.in_(_DECIDED_STATUSES),
        PhaseChangeRequest.reviewed_at.is_not(None),
        PhaseChangeRequest.reviewed_at >= dt_lo,
        PhaseChangeRequest.reviewed_at < dt_hi,
    )
    if project_id is not None:
        req_q = req_q.where(PhaseChangeRequest.project_id == project_id)
    reqs = db.scalars(req_q).all()
    if market_ids is not None:
        reqs = [r for r in reqs if r.project_id in market_ids]

    # 数据起点注：data_change_events 首事件日（全局，历史不回填——不硬编码日期字面）
    first_event_at = db.scalar(
        select(DataChangeEvent.created_at).order_by(DataChangeEvent.created_at).limit(1)
    )

    return {
        "days": days,
        "data_start": first_event_at.date().isoformat() if first_event_at else None,
        "plan_stability": plan_rows,
        "estimation_deviation": est_rows,
        "approval_latency": _approval_latency(reqs),
        "move_parse_skipped": move_parse_skipped,
        "first_plan_skipped": first_plan_skipped,
    }
