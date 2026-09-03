"""首页看板 API：聚合统计数据。

对应 PROJECT_SPEC §6.1 Dashboard。
- GET /api/dashboard/stats：一次返回所有看板数据
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, Project
from app.schemas import (
    DashboardStats,
    DelayedPhase,
    DelayedProject,
    DueSoonPhase,
    ReworkPhase,
    StatusCount,
)
from app.services.resource_conflicts import detect_conflicts

router = APIRouter(prefix="/api/dashboard", tags=["看板"])

# 未完成状态（参与延期/到期判定）
_ACTIVE_STATUSES = ("未开始", "进行中")
# 项目级搁置状态（PROJECT_SHELVE §2.2/决策 4；2026-08-28 起旧值「已搁置」兼容已移除）：
# 搁置项目 = 假完成，其阶段不参与任何阶段级报警
_SHELVED_PROJECT_STATUSES = ("搁置",)
# 即将到期窗口（天）
_DUE_SOON_DAYS = 7


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """首页看板聚合统计：项目/阶段状态分布、延期预警、返工统计。"""
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
