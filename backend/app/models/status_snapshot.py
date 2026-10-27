"""status_snapshots（每日状态快照）模型（PROJECT_ANALYSIS §3.1）。

- 每日一行：snapshot_date 唯一约束保证幂等（当日已有即跳过）
- metrics 存原子计数 JSON：比率/差分在查询时计算——未来加图不改历史快照结构
- SQLAlchemy JSON 类型（SQLite/PG 通吃）；生产 PG 由 deploy/migrate_v4.sql 建 JSONB 列
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StatusSnapshot(Base):
    __tablename__ = "status_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
