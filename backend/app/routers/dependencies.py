"""依赖关系 API 路由。

对应 PROJECT_SPEC §4.2 依赖关系端点。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dependency, Phase, Project
from app.schemas import DependencyCreate, DependencyRead

router = APIRouter(tags=["依赖关系"])


def _validate(db: Session, dep: DependencyCreate) -> None:
    if dep.from_phase_id == dep.to_phase_id:
        raise HTTPException(400, "依赖的前置与后续阶段不能是同一个阶段")
    from_ph = db.get(Phase, dep.from_phase_id)
    to_ph = db.get(Phase, dep.to_phase_id)
    if from_ph is None or to_ph is None:
        raise HTTPException(400, "前置或后续阶段不存在")
    if from_ph.project_id != to_ph.project_id:
        raise HTTPException(400, "依赖只能建立在同一项目的阶段之间")
    exists = db.scalars(
        select(Dependency).where(
            Dependency.from_phase_id == dep.from_phase_id,
            Dependency.to_phase_id == dep.to_phase_id,
        )
    ).first()
    if exists:
        raise HTTPException(400, "该依赖关系已存在")


@router.get(
    "/api/projects/{project_id}/dependencies",
    response_model=list[DependencyRead],
)
def list_dependencies(project_id: int, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "项目不存在")
    return list(
        db.execute(
            select(Dependency)
            .join(Phase, Dependency.from_phase_id == Phase.id)
            .where(Phase.project_id == project_id)
        ).scalars()
    )


@router.post(
    "/api/projects/{project_id}/dependencies",
    response_model=DependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    project_id: int, payload: DependencyCreate, db: Session = Depends(get_db)
):
    _validate(db, payload)
    dep = Dependency(**payload.model_dump())
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


@router.delete("/api/dependencies/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dependency(dep_id: int, db: Session = Depends(get_db)):
    dep = db.get(Dependency, dep_id)
    if dep is None:
        raise HTTPException(404, "依赖关系不存在")
    db.delete(dep)
    db.commit()
