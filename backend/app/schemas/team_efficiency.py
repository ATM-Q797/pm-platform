"""团队效率 schema（PHASE8_PLAN §四 8-4）。"""
from __future__ import annotations

from pydantic import BaseModel


class PersonMetrics(BaseModel):
    resource_id: int
    name: str
    role: str | None = None
    active_projects: int = 0
    peak_parallel: int = 0
    on_time_rate: float | None = None
    on_time_sample: str = "0/0"
    rework_rate: float | None = None
    avg_cycle_days: float | None = None
    active_phases: int = 0


class EfficiencySummary(BaseModel):
    completion_date_record_rate: float | None = None
    total_phases: int = 0
    dated_phases: int = 0
    window_label: str = ""


class RoleLoad(BaseModel):
    role: str
    project_count: int


class ReworkTopItem(BaseModel):
    role: str
    count: int


class TeamEfficiency(BaseModel):
    window_days: int
    summary: EfficiencySummary
    persons: list[PersonMetrics]
    role_load: dict[str, int]
    rework_top: list[ReworkTopItem]
