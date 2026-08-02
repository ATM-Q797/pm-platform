"""phase（阶段实例）/ phase_assignee（多对多）/ rework_log（返工日志）模型。

对应 schema.sql 第 6、7、9 张表。phase_assignee 作为多对多关联表用 Table 直接定义。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.resource import Resource


# phase_assignee 多对多关联表（复合主键）
phase_assignee = Table(
    "phase_assignee",
    Base.metadata,
    Column("phase_id", ForeignKey("phase.id", ondelete="CASCADE"), primary_key=True),
    Column("resource_id", ForeignKey("resource.id", ondelete="CASCADE"), primary_key=True),
)


class Phase(Base):
    __tablename__ = "phase"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # P1-P8
    name: Mapped[str] = mapped_column(String, nullable=False)  # 阶段显示名称
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # 项目内顺序
    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="未开始", server_default="未开始", index=True
    )  # 未开始/进行中/已完成/延期/已搁置
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0-100
    rework_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    handover_to: Mapped[str | None] = mapped_column(String)
    remark: Mapped[str | None] = mapped_column(String)

    project: Mapped["Project"] = relationship(back_populates="phases")
    assignees: Mapped[list["Resource"]] = relationship(
        secondary=phase_assignee, back_populates="phases", lazy="selectin"
    )
    rework_logs: Mapped[list["ReworkLog"]] = relationship(
        back_populates="phase", cascade="all, delete-orphan", lazy="selectin"
    )


class ReworkLog(Base):
    __tablename__ = "rework_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phase_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String, nullable=False)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    phase: Mapped["Phase"] = relationship(back_populates="rework_logs")
