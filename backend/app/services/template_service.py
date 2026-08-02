"""模板应用：把模板的 phases + dependencies 复制为项目实际的 phase / dependency。

调用 POST /api/projects/{id}/apply-template/{template_id} 时使用。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project, Template


def apply_template(db: Session, project_id: int, template_id: int) -> list[Phase]:
    """从模板复制阶段与依赖到项目。返回新建的阶段列表。

    - 阶段：phase_type / name / sequence 照搬模板，工期取模板默认值，
      plan_start 默认设为今天，plan_end = plan_start + 工期。
    - 依赖：按模板里 from_phase_type / to_phase_type 匹配阶段（同类型同名优先；
      若同类型有多阶段则按 sequence 映射模板顺序）。
    """
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    template = db.get(Template, template_id)
    if template is None:
        raise ValueError(f"模板 {template_id} 不存在")

    tpl_phases = template.phases
    tpl_deps = template.dependencies

    # 1. 复制阶段
    created_phases: list[Phase] = []
    base_date = project.plan_start or date.today()
    # 每个 phase_type 累计偏移，串行排工期（简化：按 sequence 累加）
    cursor = base_date
    for tp in sorted(tpl_phases, key=lambda x: x.sequence):
        plan_start = cursor
        plan_end = plan_start + timedelta(days=max(tp.default_duration_days, 1))
        ph = Phase(
            project_id=project_id,
            phase_type=tp.phase_type,
            name=tp.name,
            sequence=tp.sequence,
            plan_start=plan_start,
            plan_end=plan_end,
            status="未开始",
            progress=0,
            rework_count=0,
        )
        db.add(ph)
        created_phases.append(ph)
        cursor = plan_end
    db.flush()  # 拿到 phase.id

    # 2. 建立两套定位映射：
    #    - seq_to_phase：sequence → 阶段（精确，用于模板B等同类型多阶段）
    #    - type_to_phase：phase_type → 该类型的第一个阶段（粗略，用于模板A/C，每个类型唯一）
    seq_to_phase: dict[int, Phase] = {ph.sequence: ph for ph in created_phases}
    type_to_phase: dict[str, Phase] = {}
    for ph in created_phases:
        type_to_phase.setdefault(ph.phase_type, ph)

    def _resolve(seq: int | None, phase_type: str) -> Phase | None:
        """优先按 sequence 精确定位，其次按 phase_type 取第一个。"""
        if seq is not None:
            return seq_to_phase.get(seq)
        return type_to_phase.get(phase_type)

    for td in tpl_deps:
        from_ph = _resolve(td.from_seq, td.from_phase_type)
        to_ph = _resolve(td.to_seq, td.to_phase_type)
        if from_ph is None or to_ph is None:
            # 定位失败（phase_type 在模板 phases 中不存在），跳过
            continue
        if from_ph.id == to_ph.id:
            continue
        # 避免重复依赖
        exists = db.scalars(
            select(Dependency).where(
                Dependency.from_phase_id == from_ph.id,
                Dependency.to_phase_id == to_ph.id,
            )
        ).first()
        if exists:
            continue
        db.add(
            Dependency(
                from_phase_id=from_ph.id,
                to_phase_id=to_ph.id,
                type=td.type,
                lag_days=td.lag_days,
            )
        )

    # 关联模板到项目
    project.template_id = template_id
    db.flush()
    return created_phases
