"""删除申请 + 操作日志的 Pydantic 模型（Phase 5.3）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeleteRequestCreate(BaseModel):
    """负责人申请删除项目。"""
    reason: str | None = None


class DeleteRequestRead(BaseModel):
    """删除申请详情。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    project_name: str | None = None
    project_code: str | None = None
    requested_by: int
    requester_name: str | None = None
    reason: str | None = None
    status: str
    reviewed_by: int | None = None
    review_comment: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None


class DeleteReview(BaseModel):
    """管理员审核删除申请。"""
    approved: bool
    comment: str | None = None


class OperationLogRead(BaseModel):
    """操作日志条目。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_name: str | None = None
    action: str
    target_type: str
    target_id: int | None = None
    target_name: str | None = None
    detail: str | None = None
    created_at: datetime | None = None


# ---------- 过程事件（P1 过程事件地基，PHASE8_PLAN §九） ----------

class DataChangeEventRead(BaseModel):
    """过程事件条目：字段级审计（谁/何时/项目/字段/原值→新值/来源/理由）。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    phase_id: int | None = None
    field: str
    field_label: str | None = None  # 中文标签（读取侧映射，不入库）
    old_value: str | None = None
    new_value: str | None = None
    source: str
    changed_by: int | None = None
    changed_by_name: str | None = None
    project_name: str | None = None
    phase_name: str | None = None
    reason: str | None = None
    created_at: datetime | None = None


# ---------- 阶段编辑审批 ----------

class PhaseChangeRequestCreate(BaseModel):
    """工程师提交阶段编辑审批。"""
    phase_id: int
    proposed_changes: dict  # {field: new_value, ...}


class PhaseChangeRequestRead(BaseModel):
    """阶段变更审批详情。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    phase_id: int
    phase_name: str | None = None
    project_id: int
    project_name: str | None = None
    requested_by: int
    requester_name: str | None = None
    proposed_changes: str | None = None  # JSON string
    status: str
    reviewed_by: int | None = None
    review_comment: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None


class PhaseChangeReview(BaseModel):
    """管理员审核阶段变更。"""
    approved: bool
    comment: str | None = None
