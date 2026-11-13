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


# ---------- P3 过程事件审计分析（PHASE8_PLAN §九，批次档 P3过程事件审计分析-2026-11-12 §2） ----------

class PlanStabilityRow(BaseModel):
    """计划稳定性项目行：窗口内计划字段变更事件次数 + 累计挪动天数（按字段变更事件计）。"""
    project_id: int | None  # 被删项目事件（SET NULL 追溯）为 None，按冗余 project_name 归行
    project_name: str | None
    change_count_project: int  # plan_start/plan_end 事件条数
    change_count_phase: int  # phase_plan_start/phase_plan_end 事件条数
    move_days_project: int  # Σ|new−old|（天）
    move_days_phase: int
    move_days_total: int


class EstimationDeviationRow(BaseModel):
    """估算偏差阶段行：首次计划（按字段独立取首值再成对）vs 实际；仅 actual_end 非空阶段。"""
    project_id: int
    project_name: str | None
    phase_id: int
    phase_name: str | None
    first_plan_start: str  # YYYY-MM-DD（两字段首值成对可用才入行）
    first_plan_end: str
    actual_start: str | None
    actual_end: str  # YYYY-MM-DD
    plan_duration_days: int  # first_plan_end − first_plan_start
    actual_duration_days: int | None  # actual_end − actual_start；actual_start 为空则不可算
    deviation_days: int | None  # 实际工期 − 首次计划工期
    delivery_deviation_days: int  # actual_end − first_plan_end（与偏差天数并列展示）


class ApprovalLatency(BaseModel):
    """审批时效：改期申请「提交→决于」（「批下来」按「决于」读，含驳回件；仅 approved 均值可切换）。"""
    avg_hours: float | None  # 已决（approved/rejected）均值；无样本 None（不冒充 0）
    count: int
    approved_avg_hours: float | None  # 仅 approved 均值（切换展示用）
    approved_count: int


class ProcessAuditResult(BaseModel):
    """过程审计三指标聚合响应：不设按人（changed_by）聚合维度（不做绩效评分/排名）。"""
    days: int
    data_start: str | None  # 数据起点 = data_change_events 首事件日（历史不回填，动态取不硬编码）
    plan_stability: list[PlanStabilityRow]
    estimation_deviation: list[EstimationDeviationRow]
    approval_latency: ApprovalLatency
    move_parse_skipped: int  # 计划变更事件日期解析失败条数（显式返回，不静默丢弃、不计天数）
    first_plan_skipped: int  # 首次计划首值成对缺失阶段数（显式计数，不计入明细）
