"""模板 API 路由。

对应 PROJECT_SPEC §4.2 模板端点。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Template, TemplateDependency, TemplatePhase
from app.schemas import TemplateCreate, TemplateRead, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["模板"])


@router.get("", response_model=list[TemplateRead])
@router.get("/", response_model=list[TemplateRead], include_in_schema=False)
def list_templates(db: Session = Depends(get_db)):
    return list(db.scalars(select(Template).order_by(Template.id)))


@router.get("/{template_id}", response_model=TemplateRead)
def get_template(template_id: int, db: Session = Depends(get_db)):
    tpl = db.get(Template, template_id)
    if tpl is None:
        raise HTTPException(404, "模板不存在")
    return tpl


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    if db.scalars(select(Template).where(Template.name == payload.name)).first():
        raise HTTPException(400, f"模板 {payload.name} 已存在")
    tpl = Template(name=payload.name, category=payload.category, description=payload.description)
    db.add(tpl)
    db.flush()
    for ph in payload.phases:
        db.add(
            TemplatePhase(
                template_id=tpl.id,
                phase_type=ph.phase_type,
                name=ph.name,
                sequence=ph.sequence,
                default_duration_days=ph.default_duration_days,
                default_assignee_role=ph.default_assignee_role,
            )
        )
    for dep in payload.dependencies:
        db.add(
            TemplateDependency(
                template_id=tpl.id,
                from_phase_type=dep.from_phase_type,
                to_phase_type=dep.to_phase_type,
                from_seq=dep.from_seq,
                to_seq=dep.to_seq,
                type=dep.type,
                lag_days=dep.lag_days,
            )
        )
    db.commit()
    db.refresh(tpl)
    return tpl


@router.put("/{template_id}", response_model=TemplateRead)
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db)):
    tpl = db.get(Template, template_id)
    if tpl is None:
        raise HTTPException(404, "模板不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(tpl, k, v)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    tpl = db.get(Template, template_id)
    if tpl is None:
        raise HTTPException(404, "模板不存在")
    db.delete(tpl)
    db.commit()
