"""首页看板的 Pydantic 响应模型。"""
from __future__ import annotations

from pydantic import BaseModel


class StatusCount(BaseModel):
    """状态计数项。"""
    status: str
    count: int


class DelayedProject(BaseModel):
    """延期预警项。"""
    id: int
    code: str
    name: str
    owner: str
    market: str
    status: str
    plan_end: str | None  # YYYY-MM-DD
    overdue_days: int  # 逾期天数（今天 - plan_end）


class ReworkPhase(BaseModel):
    """返工阶段项。"""
    phase_id: int
    phase_name: str
    project_id: int
    project_name: str
    rework_count: int


class DashboardStats(BaseModel):
    """首页看板聚合统计数据（一次请求返回全部）。"""
    # 顶部统计卡片
    total_projects: int
    active_projects: int  # 进行中
    delayed_count: int  # 延期项目数
    total_phases: int
    # 项目状态分布
    project_status: list[StatusCount]
    # 阶段状态分布
    phase_status: list[StatusCount]
    # 延期预警列表（按逾期天数倒序）
    delayed_projects: list[DelayedProject]
    # 返工统计
    total_rework_count: int  # 返工总次数
    rework_phases: list[ReworkPhase]  # 有返工的阶段（按返工次数倒序）
