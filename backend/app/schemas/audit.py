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
