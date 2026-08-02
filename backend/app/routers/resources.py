"""资源/人员 API 路由，含负载查询。

对应 PROJECT_SPEC §4.2 资源/人员端点。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, Resource
from app.schemas import ResourceCreate, ResourceRead, ResourceUpdate, ResourceWorkload

router = APIRouter(prefix="/api/resources", tags=["资源/人员"])


@router.get("", response_model=list[ResourceRead])
@router.get("/", response_model=list[ResourceRead], include_in_schema=False)
def list_resources(db: Session = Depends(get_db)):
    return list(db.scalars(select(Resource).order_by(Resource.id)))


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    if db.scalars(select(Resource).where(Resource.name == payload.name)).first():
        raise HTTPException(400, f"人员 {payload.name} 已存在")
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.put("/{resource_id}", response_model=ResourceRead)
def update_resource(resource_id: int, payload: ResourceUpdate, db: Session = Depends(get_db)):
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
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
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
    workloads = [
        {
            "project_id": ph.project_id,
            "project_name": ph.project.name,
            "phase_id": ph.id,
            "phase_name": ph.name,
            "plan_start": ph.plan_start.isoformat() if ph.plan_start else None,
            "period": [
                ph.plan_start.isoformat() if ph.plan_start else None,
                ph.plan_end.isoformat() if ph.plan_end else None,
            ],
        }
        for ph in phases
    ]
    return ResourceWorkload(
        resource={"id": resource.id, "name": resource.name, "role": resource.role},
        workloads=workloads,
    )
