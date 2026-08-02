"""template / template_phase / template_dependency 模型。

对应 schema.sql 第 2、3、4 张表。模板是"标准流程蓝图"，新建项目时复制为
实际的 phase 与 dependency。
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Template(Base):
    __tablename__ = "template"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String, nullable=False)  # 新需求研发/量产交付/定制改造
    description: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    phases: Mapped[list["TemplatePhase"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", lazy="selectin"
    )
    dependencies: Mapped[list["TemplateDependency"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", lazy="selectin"
    )
    projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]
        back_populates="template"
    )


class TemplatePhase(Base):
    __tablename__ = "template_phase"
    __table_args__ = (
        UniqueConstraint("template_id", "sequence", name="uq_template_phase_seq"),
        UniqueConstraint("template_id", "phase_type", "name", name="uq_template_phase_type_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("template.id", ondelete="CASCADE"), nullable=False
    )
    phase_type: Mapped[str] = mapped_column(String, nullable=False)  # P1-P8
    name: Mapped[str] = mapped_column(String, nullable=False)  # 显示名称
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # 模板内顺序
    default_duration_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    default_assignee_role: Mapped[str | None] = mapped_column(String)

    template: Mapped["Template"] = relationship(back_populates="phases")


class TemplateDependency(Base):
    __tablename__ = "template_dependency"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("template.id", ondelete="CASCADE"), nullable=False
    )
    from_phase_type: Mapped[str] = mapped_column(String, nullable=False)
    to_phase_type: Mapped[str] = mapped_column(String, nullable=False)
    # 可选：用 sequence 精确定位模板阶段。当模板内同 phase_type 有多个阶段（如模板B的多个P8）
    # 时，phase_type 无法区分，需用 sequence。为空时按 phase_type 匹配（兼容模板A/C）。
    from_seq: Mapped[int | None] = mapped_column(Integer)
    to_seq: Mapped[int | None] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String, nullable=False, default="FS", server_default="FS")  # FS/SS/FF/SF
    lag_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    template: Mapped["Template"] = relationship(back_populates="dependencies")
