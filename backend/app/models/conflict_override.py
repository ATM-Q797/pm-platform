"""conflict_override — 资源冲突消除记录（CONFLICT_MODEL_V2 v2.1 按阶段语义）。

v2.1：消除粒度 = 资源 × 阶段（甘特条）——该阶段不计入该资源的并行计算。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class ConflictOverride(Base):
    __tablename__ = "conflict_override"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(Integer, ForeignKey("resource.id", ondelete="CASCADE"), nullable=False)
    phase_id = Column(Integer, ForeignKey("phase.id", ondelete="CASCADE"), nullable=False)
    reason = Column(String(500), nullable=False)
    created_by = Column(Integer, ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("resource_id", "phase_id", name="uq_override_resource_phase"),)

    resource = relationship("Resource")
    phase = relationship("Phase")
