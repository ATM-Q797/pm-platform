"""Phase / ReworkLog 的 Pydantic 模型。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resource import ResourceRead


class PhaseBase(BaseModel):
    phase_type: str  # P1-P8
    name: str
    sequence: int
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    status: str = "未开始"  # 未开始/进行中/已完成/延期/已搁置
    progress: int = Field(default=0, ge=0, le=100)
    rework_count: int = 0
    remark: str | None = None


class PhaseCreate(PhaseBase):
    # 创建时可顺便指定负责人（resource id 列表），可选
    assignee_ids: list[int] = []
    # 创建时可顺便指定前置阶段（phase id 列表，可选，空=无依赖也合法）。
    # 后端会为每个前置 id 自动建一条 前置→当前 的 FS 依赖。
    depends_on_phase_ids: list[int] = []
    # 创建时可指定后续阶段（phase id 列表，可选，空=无依赖也合法）。
    # 后端会为每个后续 id 自动建一条 当前→后续 的 FS 依赖。
    depended_by_phase_ids: list[int] = []


class PhaseUpdate(BaseModel):
    phase_type: str | None = None
    name: str | None = None
    sequence: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    status: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    rework_count: int | None = None
    remark: str | None = None
    assignee_ids: list[int] | None = None  # 提供则整体替换负责人


class PhaseRead(PhaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    assignees: list[ResourceRead] = []


class ReworkRequest(BaseModel):
    """阶段返工：把状态回退到目标状态，写一条返工日志。"""
    to_status: str = "未开始"
    reason: str


class ReworkLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phase_id: int
    from_status: str
    to_status: str
    reason: str
    created_at: datetime | None = None
