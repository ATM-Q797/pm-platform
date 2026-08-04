"""删除申请 + 操作日志模型（Phase 5.3）。

- ProjectDeleteRequest：项目负责人申请删除项目，管理员审核
- OperationLog：关键操作审计日志
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class ProjectDeleteRequest(Base):
    """项目删除申请。

    流程：负责人申请(status=pending) → 管理员通过(approved→真删) 或 拒绝(rejected→恢复)。
    同一项目同时只能有一个 pending 申请。
    """
    __tablename__ = "project_delete_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending", index=True)
    # pending / approved / rejected
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship()
    requester: Mapped["User"] = relationship(foreign_keys=[requested_by])


class OperationLog(Base):
    """操作审计日志：记录谁在什么时候对什么做了什么。"""
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"), index=True)
    user_name: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # create_project / update_project / delete_project / update_phase / rework_phase / approve_delete ...
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    # project / phase / template ...
    target_id: Mapped[int | None] = mapped_column(Integer)
    target_name: Mapped[str | None] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
