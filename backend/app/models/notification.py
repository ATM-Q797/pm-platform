"""站内通知模型（二期①，用户 2026-11-04）。

为什么独立文件：通知是跨流程能力（本期由改期审批产生，后续其他流程可复用），
不塞进 audit.py——审计日志是「谁在什么时候改了什么」，通知是「发给谁的一条消息」，
两者的生命周期与查询方式都不同（审计永久留痕、通知可已读可清理）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    """站内通知：收件人为单个账号，read_at 为空即未读。"""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True)
    # change_request_created / change_request_approved /
    # change_request_rejected / change_request_invalidated
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String)  # 前端跳转路径（如 /report）
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), index=True)
