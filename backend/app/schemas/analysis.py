"""项目分析的 Pydantic 响应模型（PROJECT_ANALYSIS §3.2）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SnapshotRunResult(BaseModel):
    """手动快照触发结果：created=false 表示当日已有（幂等跳过）。"""
    snapshot_date: str  # YYYY-MM-DD
    created: bool
    metrics: dict[str, Any]


class TrendPoint(BaseModel):
    """日级点位：快照原子计数原样透出（比率/差分由前端按需计算）。"""
    date: str  # YYYY-MM-DD
    metrics: dict[str, Any]


class WeeklyPoint(BaseModel):
    """周级聚合点（周一锚点）：metrics 取周内最后一个快照；delta 为相邻周差分。"""
    week_start: str  # YYYY-MM-DD（周一）
    metrics: dict[str, Any]
    delta: dict[str, int]  # 仅累计量键（completed_phases_total/shelved_total/projects_total）；首周为 0


class AnalysisTrend(BaseModel):
    """趋势数据：days 窗口 + 日级点位 + 周级聚合。"""
    days: int
    daily: list[TrendPoint]
    weekly: list[WeeklyPoint]
