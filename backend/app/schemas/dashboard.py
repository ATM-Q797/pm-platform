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
    due_phases: list[str] = []  # 该项目内已逾期的活跃阶段名（看板今日聚焦展示）


class ReworkPhase(BaseModel):
    """返工阶段项。"""
    phase_id: int
    phase_name: str
    project_id: int
    project_name: str
    rework_count: int


# ---------- T5：阶段级延期 / 即将到期 / 冲突计数 ----------

class DelayedPhase(BaseModel):
    """阶段级实际延期项（计算式，不写库）。"""
    phase_id: int
    phase_name: str
    project_id: int
    project_name: str
    overdue_days: int  # 逾期天数（今天 - plan_end）


class DueSoonPhase(BaseModel):
    """即将到期阶段项（未来 7 天内到期且未完成）。"""
    phase_id: int
    phase_name: str
    project_id: int
    project_name: str
    days_left: int  # 剩余天数（plan_end - 今天）


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
    # T5：阶段级预警 + 冲突
    delayed_phases: list[DelayedPhase] = []  # 阶段级实际延期（按逾期天数倒序）
    due_soon_phases: list[DueSoonPhase] = []  # 即将到期阶段（按剩余天数升序）
    due_soon_count: int = 0  # 即将到期阶段数
    conflict_count: int = 0  # 资源冲突对数（复用 T4 检测）
