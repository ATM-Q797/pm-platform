"""甘特图数据组装。

把一个项目的 phases + dependencies 转换为 dhtmlxGantt 兼容格式。
- 顶层一条 type=project 的项目行（id 取负数避免与 phase 冲突，parent=0）
- 每个阶段一条 type=task 的行，parent 指向项目行
- links 由 dependency 生成，type 映射：FS→"0" SS→"1" FF→"2" SF→"3"
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project
from app.schemas import GanttData, GanttLink, GanttTask

# dhtmlxGantt link type 映射
_LINK_TYPE_MAP = {"FS": "0", "SS": "1", "FF": "2", "SF": "3"}


def _diff_days(start: date | None, end: date | None) -> int:
    """两个日期间隔天数；任一为空返回 1（dhtmlx 至少需要 1 天）。"""
    if not start or not end:
        return 1
    delta = (end - start).days
    return delta if delta > 0 else 1


def build_gantt(db: Session, project_id: int) -> GanttData | None:
    project = db.get(Project, project_id)
    if project is None:
        return None

    # 项目行 id 用负数，避免与 phase.id（从 1 自增）冲突；dhtmlxGantt 只要求唯一。
    project_row_id = -project_id

    # 项目整体进度：取各阶段 progress 的平均
    phases = project.phases
    avg_progress = (sum(p.progress for p in phases) / len(phases) / 100.0) if phases else 0.0

    tasks: list[GanttTask] = [
        GanttTask(
            id=project_row_id,
            text=project.name,
            start_date=project.plan_start.isoformat() if project.plan_start else date.today().isoformat(),
            duration=_diff_days(project.plan_start, project.plan_end),
            progress=round(avg_progress, 2),
            parent=0,
            type="project",
            open=True,
        )
    ]

    for ph in sorted(phases, key=lambda p: p.sequence):
        start = ph.plan_start or ph.actual_start
        end = ph.plan_end or ph.actual_end
        tasks.append(
            GanttTask(
                id=ph.id,
                text=ph.name,
                start_date=start.isoformat() if start else date.today().isoformat(),
                duration=_diff_days(start, end),
                progress=round(ph.progress / 100.0, 2),
                parent=project_row_id,
                type="task",
                open=True,
                rework_count=ph.rework_count,
                remark=ph.remark,  # 甘特悬浮显示备注（SPECIAL_PROJECT §五）
            )
        )

    # 依赖关系 → links（取该项目的所有 dependency）
    dep_rows = db.execute(
        select(Dependency).join(Phase, Dependency.from_phase_id == Phase.id).where(Phase.project_id == project_id)
    ).scalars().all()

    links = [
        GanttLink(
            id=d.id,
            source=d.from_phase_id,
            target=d.to_phase_id,
            type=_LINK_TYPE_MAP.get(d.type, "0"),
            lag=d.lag_days,
        )
        for d in dep_rows
    ]

    return GanttData(data=tasks, links=links)
