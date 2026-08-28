"""project（项目）模型。

对应 schema.sql 第 5 张表。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.phase import Phase
    from app.models.template import Template
    from app.models.user import User


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)  # 项目编号
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 新需求/量产/定制/改造
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 国内/海外
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="未开始", server_default="未开始", index=True
    )  # 未开始/进行中/已完成/搁置（PROJECT_SHELVE §2.1）
    priority: Mapped[str | None] = mapped_column(String)  # 高/中/低
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("template.id"))
    remark: Mapped[str | None] = mapped_column(String)
    # 专项项目标记（SPECIAL_PROJECT §一）：专项项目独立监控，不占资源负载/普通列表
    is_special: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    # Phase 5：项目负责人（user 关联）+ 创建者
    managed_by: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    template: Mapped["Template | None"] = relationship(back_populates="projects")
    manager: Mapped["User | None"] = relationship(foreign_keys=[managed_by])
    phases: Mapped[list["Phase"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
