"""阶段相关 API 路由。

对应 PROJECT_SPEC §4.2 阶段端点，含返工 (/rework)。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, check_project_access, check_phase_access
from app.database import get_db
from app.models import Dependency, Phase, Project, Resource, ReworkLog, User
from app.schemas import PhaseCreate, PhaseRead, PhaseUpdate, ReworkLogRead, ReworkRequest

router = APIRouter(tags=["阶段"])


def _sync_assignees(db: Session, phase: Phase, assignee_ids: list[int]) -> None:
    """根据 id 列表整体替换阶段负责人。"""
    resources = list(db.scalars(select(Resource).where(Resource.id.in_(assignee_ids))))
    found_ids = {r.id for r in resources}
    missing = set(assignee_ids) - found_ids
    if missing:
        raise HTTPException(400, f"人员 id 不存在: {sorted(missing)}")
    phase.assignees = resources


def _normalize_sequence(db: Session, project_id: int) -> None:
    """重排项目内所有阶段的 sequence，保证连续无空洞（1,2,3...）。

    在 create/update/delete/move 后调用，彻底避免 sequence 空洞或重复。
    """
    phases = list(
        db.scalars(
            select(Phase).where(Phase.project_id == project_id).order_by(Phase.sequence, Phase.id)
        )
    )
    for idx, ph in enumerate(phases, start=1):
        if ph.sequence != idx:
            ph.sequence = idx


def _create_prerequisite_dependencies(
    db: Session, project_id: int, current_phase_id: int, prerequisite_ids: list[int]
) -> None:
    """为当前阶段批量创建「前置 → 当前」的 FS 依赖。

    - 前置阶段必须存在且属于同一项目，否则报 400
    - 不能自引用（前置不能是自己）——理论上不会发生，因为当前阶段刚 flush 出 id，
      但为防御仍校验
    - 已存在的依赖跳过（不报错），保证幂等
    """
    # 一次性查出所有前置阶段并校验归属
    prereqs = list(db.scalars(select(Phase).where(Phase.id.in_(prerequisite_ids))))
    found_ids = {p.id for p in prereqs}
    missing = set(prerequisite_ids) - found_ids
    if missing:
        raise HTTPException(400, f"前置阶段 id 不存在: {sorted(missing)}")
    for p in prereqs:
        if p.project_id != project_id:
            raise HTTPException(400, f"前置阶段 {p.id} 不属于项目 {project_id}")
        if p.id == current_phase_id:
            raise HTTPException(400, "前置阶段不能是阶段自身")
    # 查已存在的依赖，幂等跳过
    existing = set(
        db.scalars(
            select(Dependency.from_phase_id).where(
                Dependency.to_phase_id == current_phase_id,
                Dependency.from_phase_id.in_(prerequisite_ids),
            )
        )
    )
    for pid in prerequisite_ids:
        if pid in existing:
            continue
        db.add(
            Dependency(
                from_phase_id=pid,
                to_phase_id=current_phase_id,
                type="FS",
                lag_days=0,
            )
        )


@router.get("/api/projects/{project_id}/phases", response_model=list[PhaseRead])
def list_phases(project_id: int, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "项目不存在")
    return list(db.scalars(select(Phase).where(Phase.project_id == project_id).order_by(Phase.sequence)))


@router.get("/api/phases/{phase_id}", response_model=PhaseRead)
def get_phase(phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        raise HTTPException(404, "阶段不存在")
    return phase


@router.post(
    "/api/projects/{project_id}/phases",
    response_model=PhaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_phase(
    project_id: int,
    payload: PhaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 检查项目存在 + 操作权限
    check_project_access(project_id, user, db)

    # sequence 处理：直接用传入值插入，后续 _normalize_sequence 会重排保证连续
    new_seq = payload.sequence
    # 将 >= 新 sequence 的已有阶段后移 1（腾出位置）
    existing = list(
        db.scalars(
            select(Phase)
            .where(Phase.project_id == project_id, Phase.sequence >= new_seq)
            .order_by(Phase.sequence.desc())
        )
    )
    for ph in existing:
        ph.sequence += 1

    data = payload.model_dump(exclude={"assignee_ids", "depends_on_phase_ids", "depended_by_phase_ids"})
    phase = Phase(**data, project_id=project_id)
    db.add(phase)
    db.flush()
    if payload.assignee_ids:
        _sync_assignees(db, phase, payload.assignee_ids)
    # 前置依赖：每个前置阶段 → 当前 的 FS 依赖
    if payload.depends_on_phase_ids:
        _create_prerequisite_dependencies(db, project_id, phase.id, payload.depends_on_phase_ids)
    # 后置依赖（新增）：当前 → 每个后续阶段 的 FS 依赖
    depended_by = getattr(payload, 'depended_by_phase_ids', None) or []
    if depended_by:
        for succ_id in depended_by:
            # 避免重复
            exists = db.scalars(
                select(Dependency).where(
                    Dependency.from_phase_id == phase.id,
                    Dependency.to_phase_id == succ_id,
                )
            ).first()
            if not exists:
                db.add(Dependency(from_phase_id=phase.id, to_phase_id=succ_id, type="FS", lag_days=0))
    # 重排 sequence 保证连续无空洞
    _normalize_sequence(db, project_id)
    db.commit()
    db.refresh(phase)
    return phase


@router.put("/api/phases/{phase_id}", response_model=PhaseRead)
def update_phase(
    phase_id: int,
    payload: PhaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 检查阶段存在 + 操作权限
    phase = check_phase_access(phase_id, user, db)
    data = payload.model_dump(exclude_unset=True)

    assignee_ids = data.pop("assignee_ids", None)
    # 如果改了 sequence，先将 >= 新值的同项目其他阶段后移，再设置新值
    if "sequence" in data and data["sequence"] != phase.sequence:
        new_seq = data["sequence"]
        existing = list(
            db.scalars(
                select(Phase)
                .where(
                    Phase.project_id == phase.project_id,
                    Phase.id != phase.id,
                    Phase.sequence >= new_seq,
                )
                .order_by(Phase.sequence.desc())
            )
        )
        for ph in existing:
            ph.sequence += 1

    for k, v in data.items():
        setattr(phase, k, v)
    if assignee_ids is not None:
        _sync_assignees(db, phase, assignee_ids)
    # 重排 sequence 保证连续无空洞
    _normalize_sequence(db, phase.project_id)
    db.commit()
    db.refresh(phase)
    return phase


@router.post("/api/phases/{phase_id}/move", response_model=PhaseRead)
def move_phase(
    phase_id: int,
    direction: str = "up",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上移/下移阶段：与视觉上相邻的阶段交换 sequence。

    - direction="up"：与上一个阶段（sequence 小于当前的最大值）交换
    - direction="down"：与下一个阶段（sequence 大于当前的最小值）交换
    基于实际 sequence 排序而非假设连续值。
    """
    phase = check_phase_access(phase_id, user, db)

    if direction == "up":
        neighbor = db.scalars(
            select(Phase).where(
                Phase.project_id == phase.project_id,
                Phase.id != phase.id,
                Phase.sequence < phase.sequence,
            ).order_by(Phase.sequence.desc()).limit(1)
        ).first()
    else:
        neighbor = db.scalars(
            select(Phase).where(
                Phase.project_id == phase.project_id,
                Phase.id != phase.id,
                Phase.sequence > phase.sequence,
            ).order_by(Phase.sequence.asc()).limit(1)
        ).first()

    if neighbor is None:
        raise HTTPException(400, "已在边界，无法继续移动")
    # 交换 sequence
    phase.sequence, neighbor.sequence = neighbor.sequence, phase.sequence
    # 重排保证连续
    _normalize_sequence(db, phase.project_id)
    db.commit()
    db.refresh(phase)
    return phase


@router.delete("/api/phases/{phase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phase(
    phase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    phase = check_phase_access(phase_id, user, db)
    project_id = phase.project_id
    db.delete(phase)
    db.flush()
    # 删除后重排剩余阶段的 sequence
    _normalize_sequence(db, project_id)
    db.commit()


@router.post("/api/phases/{phase_id}/rework", response_model=ReworkLogRead)
def rework_phase(
    phase_id: int,
    payload: ReworkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """阶段返工：回退状态 + 写返工日志 + rework_count +1。

    - 任意阶段可从 进行中/已完成 回退到目标状态（默认未开始）
    - 清空 actual_end，重新走流程
    """
    phase = check_phase_access(phase_id, user, db)
    from_status = phase.status
    log = ReworkLog(
        phase_id=phase_id,
        from_status=from_status,
        to_status=payload.to_status,
        reason=payload.reason,
    )
    phase.status = payload.to_status
    phase.rework_count = (phase.rework_count or 0) + 1
    phase.actual_end = None
    if payload.to_status == "未开始":
        phase.progress = 0
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
