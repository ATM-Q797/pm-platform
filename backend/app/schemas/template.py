"""Template / TemplatePhase / TemplateDependency 的 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplatePhaseBase(BaseModel):
    phase_type: str  # P1-P8
    name: str
    sequence: int
    default_duration_days: int = 7
    default_assignee_role: str | None = None


class TemplatePhaseCreate(TemplatePhaseBase):
    pass


class TemplatePhaseRead(TemplatePhaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int


class TemplateDependencyBase(BaseModel):
    from_phase_type: str
    to_phase_type: str
    from_seq: int | None = None  # 可选，用于精确定位同 phase_type 的多个阶段
    to_seq: int | None = None
    type: str = "FS"  # FS/SS/FF/SF
    lag_days: int = 0


class TemplateDependencyCreate(TemplateDependencyBase):
    pass


class TemplateDependencyRead(TemplateDependencyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int


class TemplateBase(BaseModel):
    name: str
    category: str
    description: str | None = None


class TemplateCreate(TemplateBase):
    phases: list[TemplatePhaseCreate] = []
    dependencies: list[TemplateDependencyCreate] = []


class TemplateUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    phases: list[TemplatePhaseRead] = []
    dependencies: list[TemplateDependencyRead] = []


# 供其它 schema 引用 Template 时只取摘要（不含子集合），避免循环
class TemplateBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
