"""首页看板 API：聚合统计数据。

对应 PROJECT_SPEC §6.1 Dashboard。
- GET /api/dashboard/stats：一次返回所有看板数据
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, Project, StatusSnapshot
from app.schemas import (
    ConflictPair,
    DashboardStats,
    DelayedPhase,
    DelayedProject,
    DueSoonPhase,
    ProjectHealthSummary,
    ResourceConflict,
    ReworkPhase,
    RiskQueueItem,
    StatusCount,
)
from app.services.health_score import assess_projects, longest_overdue_days
from app.services.resource_conflicts import detect_conflicts

router = APIRouter(prefix="/api/dashboard", tags=["看板"])

# 未完成状态（参与延期/到期判定）
_ACTIVE_STATUSES = ("未开始", "进行中")
# 项目级搁置状态（PROJECT_SHELVE §2.2/决策 4；2026-08-28 起旧值「已搁置」兼容已移除）：
# 搁置项目 = 假完成，其阶段不参与任何阶段级报警
_SHELVED_PROJECT_STATUSES = ("搁置",)
# 即将到期窗口（天）
_DUE_SOON_DAYS = 7
# 看板 4 卡环比指标键（8-1，2026-11-04 裁定：小字与卡面大数字同指标）
_CARD_DELTA_KEYS = ("projects_total", "delayed_projects", "due_soon_phases", "conflict_pairs")
# 风险队列行分组顺序（8-1，2026-11-04 裁定：逾期 → 冲突 → 到期，紧急优先）
_RISK_TYPE_RANK = {"overdue": 0, "conflict": 1, "due_soon": 2}


def build_dashboard_stats(db: Session, conflicts: list[ResourceConflict] | None = None) -> DashboardStats:
    """看板统计主体（模块级纯函数）——与每日快照共用的口径单一来源（PROJECT_ANALYSIS §3.2）。

    路由行为不变：get_dashboard_stats 仅委托本函数。
    conflicts 可传入已检冲突结果（看板路由需冲突明细建风险队列，传入避免二次全量检测）。
    """
    today = date.today()

    # 项目状态分布（专项项目独立监控，不计入看板——SPECIAL_PROJECT §4.3）
    project_status_rows = db.execute(
        select(Project.status, func.count())
        .where(Project.is_special.is_(False))
        .group_by(Project.status)
    ).all()
    project_status = [StatusCount(status=s, count=c) for s, c in project_status_rows]

    # 阶段状态分布（专项项目阶段同样排除）
    phase_status_rows = db.execute(
        select(Phase.status, func.count())
        .join(Project, Phase.project_id == Project.id)
        .where(Project.is_special.is_(False))
        .group_by(Phase.status)
    ).all()
    phase_status = [StatusCount(status=s, count=c) for s, c in phase_status_rows]

    # 延期项目（阶段锚定，方案 A 修正版，2026-09-03）：
    # 判定唯一依据 = 名下存在"已逾期活跃阶段"（阶段 plan_end < 今天 且 状态未完成/未搁置）。
    # 项目整体 plan_end 不参与判定——既非必要条件（埃塞AWASH:整体期限 9/30 未到但 3 个阶段
    # 已逾期,须报）,也不充分（阿联酋BAM-301:整体期限已过但阶段全按期完成/排期未来,不报）。
    overdue_phase_rows = db.execute(
        select(Phase.project_id, Phase.name, Phase.plan_end)
        .join(Project, Phase.project_id == Project.id)
        .where(
            Project.status.in_(_ACTIVE_STATUSES),
            Project.is_special.is_(False),
            Phase.plan_end < today,
            ~Phase.status.in_(("已完成", "搁置")),
        )
        .order_by(Phase.plan_end)
    ).all()
    overdue_phases_map: dict[int, list[str]] = {}
    overdue_anchor_map: dict[int, date] = {}  # 项目 → 最近一个已逾期阶段的 plan_end（逾期天数锚点）
    for pid, name, pend in overdue_phase_rows:
        overdue_phases_map.setdefault(pid, []).append(name)
        if pid not in overdue_anchor_map or pend < overdue_anchor_map[pid]:
            overdue_anchor_map[pid] = pend  # 最久逾期的阶段为准

    # 锚定项目集合（有逾期活跃阶段的项目 id）
    delayed_ids = list(overdue_anchor_map.keys())
    delayed = [p for p in db.scalars(select(Project).where(Project.id.in_(delayed_ids))).all()]

    delayed_projects = sorted(
        [
            DelayedProject(
                id=p.id,
                code=p.code,
                name=p.name,
                owner=p.owner,
                market=p.market,
                status=p.status,
                plan_end=p.plan_end.isoformat() if p.plan_end else None,
                overdue_days=(today - overdue_anchor_map[p.id]).days,
                due_phases=overdue_phases_map.get(p.id, []),
            )
            for p in delayed
        ],
        key=lambda d: d.overdue_days,
        reverse=True,
    )

    # 返工统计（专项项目阶段不计入）
    total_rework_count = db.execute(
        select(func.coalesce(func.sum(Phase.rework_count), 0))
        .join(Project, Phase.project_id == Project.id)
        .where(Project.is_special.is_(False))
    ).scalar() or 0
    rework_phase_rows = db.scalars(
        select(Phase)
        .join(Project, Phase.project_id == Project.id)
        .where(Phase.rework_count > 0, Project.is_special.is_(False))
        .order_by(Phase.rework_count.desc())
    ).all()
    rework_phases = [
        ReworkPhase(
            phase_id=ph.id,
            phase_name=ph.name,
            project_id=ph.project_id,
            project_name=ph.project.name,
            rework_count=ph.rework_count,
        )
        for ph in rework_phase_rows
    ]

    total_projects = sum(c for _, c in project_status_rows)
    active_projects = next((c for s, c in project_status_rows if s == "进行中"), 0)
    total_phases = sum(c for _, c in phase_status_rows)

    # ---------- T5：阶段级延期 / 即将到期 / 冲突计数 ----------
    # 阶段级实际延期：plan_end < 今天 && 状态未完成 && 所属项目未搁置且非专项（计算式，不写库）
    delayed_phase_rows = db.scalars(
        select(Phase).join(Project, Phase.project_id == Project.id).where(
            Phase.plan_end < today,
            ~Phase.status.in_(("已完成", "搁置")),  # 含"延期"状态——与 due_phases 同口径
            Project.status.not_in(_SHELVED_PROJECT_STATUSES),
            Project.is_special.is_(False),
        )
    ).all()
    delayed_phases = sorted(
        [
            DelayedPhase(
                phase_id=ph.id,
                phase_name=ph.name,
                project_id=ph.project_id,
                project_name=ph.project.name,
                overdue_days=(today - ph.plan_end).days,
            )
            for ph in delayed_phase_rows
        ],
        key=lambda d: d.overdue_days,
        reverse=True,
    )

    # 即将到期：plan_end 在未来 7 天内（含今天）&& 状态未完成 && 所属项目未搁置且非专项
    due_soon_rows = db.scalars(
        select(Phase).join(Project, Phase.project_id == Project.id).where(
            Phase.plan_end >= today,
            Phase.plan_end <= today + timedelta(days=_DUE_SOON_DAYS),
            Phase.status.in_(_ACTIVE_STATUSES),
            Project.status.not_in(_SHELVED_PROJECT_STATUSES),
            Project.is_special.is_(False),
        )
    ).all()
    due_soon_phases = sorted(
        [
            DueSoonPhase(
                phase_id=ph.id,
                phase_name=ph.name,
                project_id=ph.project_id,
                project_name=ph.project.name,
                days_left=(ph.plan_end - today).days,
            )
            for ph in due_soon_rows
        ],
        key=lambda d: d.days_left,
    )

    # 资源冲突对数（复用 T4 检测逻辑）
    if conflicts is None:
        conflicts = detect_conflicts(db)
    conflict_count = sum(len(rc.conflicts) for rc in conflicts)

    return DashboardStats(
        total_projects=total_projects,
        active_projects=active_projects,
        delayed_count=len(delayed_projects),
        total_phases=total_phases,
        project_status=project_status,
        phase_status=phase_status,
        delayed_projects=delayed_projects,
        total_rework_count=total_rework_count,
        rework_phases=rework_phases,
        delayed_phases=delayed_phases,
        due_soon_phases=due_soon_phases,
        due_soon_count=len(due_soon_phases),
        conflict_count=conflict_count,
    )


def build_risk_queue(stats: DashboardStats, conflicts: Sequence[ResourceConflict]) -> list[RiskQueueItem]:
    """今日风险队列（8-1）：延期阶段 + 即将到期阶段 + 资源冲突 三源合并去重。

    行 = 风险事件（2026-11-04 裁定）：
    - 去重：同一冲突对跨资源合并为 1 行（涉事资源并入 detail）；延期/到期按 (type, 项目, 阶段) 去重；
      跨风险类型不去重（同一阶段既逾期又卷入冲突 = 两行，两件事都要查）。
    - 排序（2026-11-04 裁定：紧急优先）：逾期（severity=3，逾期天数降序）→ 冲突（severity=2，
      重叠天数降序）→ 到期（severity=2，剩余天数升序）。
    - 冲突行取 A 侧项目为点行跳转目标，B 侧在 detail 中给出。
    """
    items: list[RiskQueueItem] = []
    seen: set[tuple] = set()

    for d in stats.delayed_phases:
        key = ("overdue", d.project_id, d.phase_id)
        if key in seen:
            continue
        seen.add(key)
        items.append(RiskQueueItem(
            project_id=d.project_id,
            project_name=d.project_name,
            phase_name=d.phase_name,
            type="overdue",
            severity=3,
            detail=f"阶段逾期 {d.overdue_days} 天",
            days=d.overdue_days,
        ))

    # 同一冲突对跨资源去重：同两阶段只算 1 行，涉事资源名合并
    pair_map: dict[tuple[int, int], tuple[ConflictPair, list[str]]] = {}
    for rc in conflicts:
        for pair in rc.conflicts:
            key = tuple(sorted((pair.phase_a_id, pair.phase_b_id)))
            if key in pair_map:
                pair_map[key][1].append(rc.resource_name)
            else:
                pair_map[key] = (pair, [rc.resource_name])
    for pair, resource_names in pair_map.values():
        items.append(RiskQueueItem(
            project_id=pair.project_a_id,
            project_name=pair.project_a_name,
            phase_name=pair.phase_a_name,
            type="conflict",
            severity=2,
            detail=f"与 {pair.project_b_name}·{pair.phase_b_name} 重叠 {pair.overlap_days} 天"
                   f"（资源：{'、'.join(resource_names)}）",
            days=pair.overlap_days,
        ))

    for s in stats.due_soon_phases:
        key = ("due_soon", s.project_id, s.phase_id)
        if key in seen:
            continue
        seen.add(key)
        items.append(RiskQueueItem(
            project_id=s.project_id,
            project_name=s.project_name,
            phase_name=s.phase_name,
            type="due_soon",
            severity=2,
            detail=f"剩余 {s.days_left} 天到期",
            days=s.days_left,
        ))

    items.sort(key=lambda r: (_RISK_TYPE_RANK[r.type], -r.days if r.type != "due_soon" else r.days, r.project_id))
    return items


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """首页看板聚合统计：分布/预警/返工 + 今日风险队列、数据截至日期与 4 卡环比、风险项目（8-2）。"""
    # 函数内导入：app.services.snapshot 顶部 import 本模块，顶层互引会成循环导入
    from app.services.snapshot import build_weekly_delta

    conflicts = detect_conflicts(db)
    stats = build_dashboard_stats(db, conflicts=conflicts)
    snapshot_date = db.scalar(
        select(StatusSnapshot.snapshot_date).order_by(StatusSnapshot.snapshot_date.desc()).limit(1)
    )

    # 风险项目（8-2）：健康度 red/yellow 升序（最危险在前）；搁置不评；专项在下方查询已排除
    risk_rows = db.scalars(
        select(Project).where(
            Project.is_special.is_(False),
            Project.status.not_in(_SHELVED_PROJECT_STATUSES),
        )
    ).all()
    health_map = assess_projects(risk_rows, conflicts, date.today())
    risk_projects = sorted(
        (
            ProjectHealthSummary(
                project_id=p.id,
                project_name=p.name,
                owner=p.owner,
                status=p.status,
                band=h.band,
                reason=h.reason,
                overdue_days=longest_overdue_days(list(p.phases), date.today()),
            )
            for p, h in ((pr, health_map[pr.id]) for pr in risk_rows if pr.id in health_map)
            if h.band in ("red", "yellow")  # 绿/灰不上卡（弹窗只关注需要处理的）
        ),
        key=lambda r: (0 if r.band == "red" else 1, -r.overdue_days, r.project_id),
    )

    return stats.model_copy(update={
        "risk_queue": build_risk_queue(stats, conflicts),
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "weekly_delta": build_weekly_delta(db, _CARD_DELTA_KEYS),
        "risk_projects": risk_projects,
    })
