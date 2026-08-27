"""conflict_override（冲突消除记录）模型。

资源 × 冲突对粒度的手动消除（CONFLICT_MODEL_V2 §2.3）：
- 只消除"某个人的实际工作量小"，不影响其他人对同一对的判定
- a/b 归一化（小 id 在前）后与 resource_id 组成 UNIQUE 约束，防重复消除
- 阶段/人员/操作人删除时级联清理
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConflictOverride(Base):
    __tablename__ = "conflict_override"
    __table_args__ = (
        # a/b 归一化后（小 id 在前）同一资源同一对只允许一条消除记录
        UniqueConstraint("resource_id", "phase_a_id", "phase_b_id", name="uq_conflict_override_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resource.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_a_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False
    )
    phase_b_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # 消除原因（必填）
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user_account.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    @staticmethod
    def normalize_pair(phase_a_id: int, phase_b_id: int) -> tuple[int, int]:
        """a/b 归一化：小 id 在前——(a,b) 与 (b,a) 视为同一对（评审处置 #3）。"""
        return (phase_a_id, phase_b_id) if phase_a_id <= phase_b_id else (phase_b_id, phase_a_id)
