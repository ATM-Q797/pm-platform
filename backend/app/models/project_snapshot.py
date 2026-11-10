"""project_snapshots（项目级快照，8-3 按项目维度的历史趋势）模型。

- PHASE8_PLAN §三 方案 A + 存储口径③（用户 2026-11-04 批复）：
  只拍在办项目（未开始/进行中），已完成/搁置项目冻结不拍。
- 每项目每日一行：唯一约束 (project_id, snapshot_date) 保证幂等（upsert 同日不重行，
  与全局快照同款）；并发兜底同 create_today_if_absent 模式。
- 冗余 project_code / project_name（快照时点值）：删项目后 project_id 被 SET NULL，
  编号是唯一可寻址键——admin 按 code 查被删项目历史曲线（追溯口径「删项目要能追溯」）。
- 外键 ON DELETE SET NULL（不用 CASCADE，用户裁定）。
- 生产 PG 用 JSONB（deploy/migrate_v6.sql）；测试 SQLite 走 SQLAlchemy JSON 通用类型。
- metrics 为快照时点定格值（plan_cum_pct / actual_cum_pct / delayed_phases / conflict_pairs），
  读时不重算——计划会改，重算会扭曲历史（§3.4 计划曲线锚定快照时点）。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"
    __table_args__ = (
        # 幂等键（与全局快照 snapshot_date 唯一同款）；生产 DDL 同名约束 uq_project_snapshots_project_date。
        # project_id 可空（SET NULL 后的追溯行）：SQLite/PG 唯一约束对 NULL 不去重，
        # 但追溯行只在项目删除时产生、此后不再新增，无并发冲突面。
        UniqueConstraint("project_id", "snapshot_date", name="uq_project_snapshots_project_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    project_code: Mapped[str | None] = mapped_column(String, index=True)
    project_name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
