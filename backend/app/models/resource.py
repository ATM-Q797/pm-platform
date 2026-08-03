"""resource（资源/人员）模型。

对应 schema.sql 第 1 张表。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.phase import Phase
    from app.models.user import User


class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    role: Mapped[str | None] = mapped_column(String)  # 岗位：工业设计/结构设计/测试/项目管理
    department: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # 反向：该人员参与的所有阶段（多对多通过 phase_assignee，关系在 phase.py 注册）
    phases: Mapped[list["Phase"]] = relationship(
        "Phase",
        secondary="phase_assignee",
        back_populates="assignees",
        lazy="select",
    )
    # 关联的登录账户（一一对应，可空）
    user: Mapped["User | None"] = relationship(back_populates="resource")
