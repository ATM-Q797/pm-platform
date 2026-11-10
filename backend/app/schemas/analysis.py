"""项目分析的 Pydantic 响应模型（PROJECT_ANALYSIS §3.2）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SnapshotRunResult(BaseModel):
    """手动快照触发结果：created=false 表示当日已有（幂等跳过）；force=true 重采覆盖当日行，created=true 表示返回新采集数据（新建或覆盖）。"""
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


# ---------- 8-3 项目趋势（PHASE8_PLAN §三，批次档 项目趋势-2026-11-10 §2） ----------

class ProjectTrendPoint(BaseModel):
    """项目趋势混合粒度点：日/周/月行统一形态，粒度标记随点携带。"""
    date: str  # YYYY-MM-DD（日=快照日；周=周一锚点；月=月初）
    granularity: str  # day | week | month
    metrics: dict[str, Any]  # 四键：plan_cum_pct / actual_cum_pct / delayed_phases / conflict_pairs


class ProjectTrendEvent(BaseModel):
    """趋势图事件点：延期/冲突取自快照 metrics（>0 的快照日），计划变更取自 data_change_events。"""
    date: str  # YYYY-MM-DD（计划变更按 changed_at 对齐时间轴）
    kind: str  # delayed | conflict | plan_change
    detail: str  # hover 明细（如「2 个阶段延期」/「计划开始 10-01 → 10-05（张三）」）


class ProjectTrend(BaseModel):
    """单项目趋势响应：混合点列 + 三类事件点 + 读口径标记。"""
    project_id: int | None  # 被删项目（by-code 追溯路径）为 None
    project_code: str | None
    project_name: str | None
    days: int
    points: list[ProjectTrendPoint]
    events: list[ProjectTrendEvent]
    frozen: bool = False  # 搁置项目 true（返回冻结前历史）
    frozen_date: str | None = None  # 冻结日 = 搁置前最后一个快照日
