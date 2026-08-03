"""首页看板 API：聚合统计数据。

对应 PROJECT_SPEC §6.1 Dashboard。
- GET /api/dashboard/stats：一次返回所有看板数据
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, Project
from app.schemas import DashboardStats, DelayedProject, ReworkPhase, StatusCount

router = APIRouter(prefix="/api/dashboard", tags=["看板"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """首页看板聚合统计：项目/阶段状态分布、延期预警、返工统计。"""
    today = date.today()

    # 项目状态分布
    project_status_rows = db.execute(
        select(Project.status, func.count()).group_by(Project.status)
    ).all()
    project_status = [StatusCount(status=s, count=c) for s, c in project_status_rows]

    # 阶段状态分布
    phase_status_rows = db.execute(
        select(Phase.status, func.count()).group_by(Phase.status)
    ).all()
    phase_status = [StatusCount(status=s, count=c) for s, c in phase_status_rows]

    # 延期项目：plan_end < 今天，且状态为 未开始/进行中（未完成、未搁置）
    delayed = db.scalars(
        select(Project).where(
            Project.plan_end < today,
            Project.status.in_(["未开始", "进行中"]),
        )
    ).all()
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
                overdue_days=(today - p.plan_end).days if p.plan_end else 0,
            )
            for p in delayed
        ],
        key=lambda d: d.overdue_days,
        reverse=True,
    )

    # 返工统计
    total_rework_count = db.execute(
        select(func.coalesce(func.sum(Phase.rework_count), 0))
    ).scalar() or 0
    rework_phase_rows = db.scalars(
        select(Phase).where(Phase.rework_count > 0).order_by(Phase.rework_count.desc())
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
    )
