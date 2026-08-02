"""Resource（资源/人员）的 Pydantic 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResourceBase(BaseModel):
    name: str
    role: str | None = None
    department: str | None = None


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    department: str | None = None


class ResourceRead(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
