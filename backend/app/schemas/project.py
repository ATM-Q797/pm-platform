"""Project 的 Pydantic 模型，以及甘特图/资源负载专用响应。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.dependency import DependencyRead
from app.schemas.phase import PhaseRead
from app.schemas.template import TemplateBrief

# 项目状态合法值（PROJECT_SHELVE §2.1：「搁置」为新名，旧值「已搁置」仅在更新时归一化接受）
PROJECT_STATUSES = ("未开始", "进行中", "已完成", "搁置")


class ProjectBase(BaseModel):
    code: str
    category: str  # 招标/量产/定制/改造
    name: str
    owner: str
    market: str  # 国内/海外
    status: str = "未开始"  # 未开始/进行中/已完成/搁置
    priority: str | None = None  # 高/中/低
    plan_start: date | None = None
    plan_end: date | None = None
    template_id: int | None = None
    remark: str | None = None
    managed_by: int | None = None  # 项目负责人 user_id


class ProjectCreate(ProjectBase):
    # 项目编号系统自动生成（连续整数），创建时可不传
    code: str | None = None


class ProjectUpdate(BaseModel):
    code: str | None = None
    category: str | None = None
    name: str | None = None
    owner: str | None = None
    market: str | None = None
    status: str | None = None
    priority: str | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    template_id: int | None = None
    remark: str | None = None
    managed_by: int | None = None  # 项目负责人 user_id

    @field_validator("status")
    @classmethod
    def _normalize_status(cls, v: str | None) -> str | None:
        """状态校验 + 旧值归一化（PROJECT_SHELVE 决策 1）。

        - 旧值「已搁置」→ 归一化为「搁置」保存（存量数据/旧客户端兼容）
        - 其他非法值 → 422
        - None / 未传 → 不校验（部分更新语义）
        """
        if v is None:
            return v
        if v == "已搁置":
            return "搁置"
        if v not in PROJECT_STATUSES:
            raise ValueError(f"非法项目状态：{v}（合法值：{'/'.join(PROJECT_STATUSES)}，旧值「已搁置」将归一化为「搁置」）")
        return v


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int | None = None  # 创建者 user_id
    created_at: datetime | None = None
    updated_at: datetime | None = None
    template: TemplateBrief | None = None
    phases: list[PhaseRead] = []
    is_favorite: bool = False  # 当前用户是否关注（列表接口填充）


class ProjectDetail(ProjectRead):
    """项目详情：额外包含依赖关系列表。"""
    dependencies: list[DependencyRead] = []


# ---------- 甘特图数据（dhtmlxGantt 兼容格式）----------

class GanttTask(BaseModel):
    id: int
    text: str
    start_date: str  # YYYY-MM-DD
    duration: int  # 天
    progress: float
    parent: int  # 0 表示顶层项目行
    type: str  # "project" | "task"
    open: bool = True
    rework_count: int | None = None


class GanttLink(BaseModel):
    id: int
    source: int
    target: int
    type: str  # "0"=FS "1"=SS "2"=FF "3"=SF
    lag: int = 0


class GanttData(BaseModel):
    data: list[GanttTask]
    links: list[GanttLink]


# ---------- 关键路径（CPM） ----------

class CriticalPathResult(BaseModel):
    """项目关键路径计算结果。"""
    critical_phase_ids: list[int]  # 关键路径上的阶段 id
    total_duration: int            # 关键路径总工期（天）
    path: list[str]                # 关键路径阶段名（按开始顺序）


# ---------- 资源负载 ----------

class WorkloadItem(BaseModel):
    project_id: int
    project_name: str
    project_owner: str | None = None  # 项目负责人（用于资源视图弹窗显示）
    phase_id: int
    phase_name: str
    plan_start: str | None
    plan_end: str | None
    status: str | None = None  # 阶段状态，用于甘特条着色
    period: list[str | None]  # [plan_start, plan_end]（兼容旧格式）


class ResourceWorkload(BaseModel):
    resource: dict[str, Any]  # {id, name, role}
    workloads: list[WorkloadItem]


# ---------- 资源冲突（T4） ----------

class ConflictPair(BaseModel):
    """一对冲突阶段。"""
    phase_a_id: int
    phase_a_name: str
    project_a_id: int
    project_a_name: str
    phase_b_id: int
    phase_b_name: str
    project_b_id: int
    project_b_name: str
    overlap_days: int


class ResourceConflict(BaseModel):
    """某资源的全部冲突对。"""
    resource_id: int
    resource_name: str
    conflicts: list[ConflictPair]
