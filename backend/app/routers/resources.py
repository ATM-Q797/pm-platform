"""资源/人员 API 路由，含负载查询。

对应 PROJECT_SPEC §4.2 资源/人员端点。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Phase, Resource, User
from app.schemas import (
    ResourceConflict,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    ResourceWorkload,
)
from app.services.resource_conflicts import detect_conflicts

router = APIRouter(prefix="/api/resources", tags=["资源/人员"])


@router.get("/conflicts", response_model=list[ResourceConflict])
def get_conflicts(db: Session = Depends(get_db)):
    """资源冲突检测：同一资源在重叠时间段被分配到不同项目的阶段。

    规则：严格重叠（背靠背不算）、同项目不算、缺日期/已完成/已搁置跳过。
    返回按资源分组，冲突对按重叠天数降序。
    """
    return detect_conflicts(db)


def _phase_to_workload(ph: Phase) -> dict:
    """把阶段转为 workload dict（get_workload / get_all_workloads 共用）。"""
    return {
        "project_id": ph.project_id,
        "project_name": ph.project.name,
        "project_owner": ph.project.owner,  # 项目负责人
        "phase_id": ph.id,
        "phase_name": ph.name,
        "plan_start": ph.plan_start.isoformat() if ph.plan_start else None,
        "plan_end": ph.plan_end.isoformat() if ph.plan_end else None,
        "status": ph.status,
        "period": [
            ph.plan_start.isoformat() if ph.plan_start else None,
            ph.plan_end.isoformat() if ph.plan_end else None,
        ],
    }


@router.get("", response_model=list[ResourceRead])
@router.get("/", response_model=list[ResourceRead], include_in_schema=False)
def list_resources(db: Session = Depends(get_db)):
    return list(db.scalars(select(Resource).order_by(Resource.id)))


@router.get("/all/workload", response_model=list[ResourceWorkload])
def get_all_workloads(db: Session = Depends(get_db)):
    """全员负载概览：一次返回所有人员的负载数据。

    用于资源负载视图（每人一行甘特图），避免前端发 N 个请求。
    按人员 id 升序，每人的阶段按 plan_start 升序。
    注意：此静态路径必须注册在 /{resource_id}/workload 之前。
    """
    resources = list(db.scalars(select(Resource).order_by(Resource.id)))
    result: list[ResourceWorkload] = []
    for res in resources:
        # 按 plan_start 排序该人员的阶段（None 排最后）
        phases = sorted(
            res.phases,
            key=lambda ph: (ph.plan_start is None, ph.plan_start or date.min),
        )
        result.append(ResourceWorkload(
            resource={"id": res.id, "name": res.name, "role": res.role},
            workloads=[_phase_to_workload(ph) for ph in phases],
        ))
    return result


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.scalars(select(Resource).where(Resource.name == payload.name)).first():
        raise HTTPException(400, f"人员 {payload.name} 已存在")
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.put("/{resource_id}", response_model=ResourceRead)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != resource.name:
        dup = db.scalars(select(Resource).where(Resource.name == data["name"])).first()
        if dup:
            raise HTTPException(400, f"人员 {data['name']} 已存在")
    for k, v in data.items():
        setattr(resource, k, v)
    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    db.delete(resource)
    db.commit()


@router.get("/{resource_id}/workload", response_model=ResourceWorkload)
def get_workload(resource_id: int, db: Session = Depends(get_db)):
    """某人负载：参与的所有项目/阶段。"""
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    phases: list[Phase] = list(resource.phases)  # 通过多对多关系
    return ResourceWorkload(
        resource={"id": resource.id, "name": resource.name, "role": resource.role},
        workloads=[_phase_to_workload(ph) for ph in phases],
    )
