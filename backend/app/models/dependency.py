"""dependency（项目阶段间依赖关系实例）模型。

对应 schema.sql 第 8 张表。from_phase_id / to_phase_id 均指向 phase。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.phase import Phase


class Dependency(Base):
    __tablename__ = "dependency"
    __table_args__ = (
        UniqueConstraint("from_phase_id", "to_phase_id", name="uq_dependency_from_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_phase_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_phase_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, default="FS", server_default="FS")  # FS/SS/FF/SF
    lag_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    from_phase: Mapped["Phase"] = relationship(foreign_keys=[from_phase_id])
    to_phase: Mapped["Phase"] = relationship(foreign_keys=[to_phase_id])
