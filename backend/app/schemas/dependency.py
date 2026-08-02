"""Dependency 的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DependencyBase(BaseModel):
    from_phase_id: int
    to_phase_id: int
    type: str = "FS"  # FS/SS/FF/SF
    lag_days: int = 0


class DependencyCreate(DependencyBase):
    pass


class DependencyRead(DependencyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
