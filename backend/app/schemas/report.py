"""信息填报模块 Pydantic 模型（信息填报一期）。

设计 docs/信息填报模块设计方案.md §五/§六——请求/响应契约；
字段级 editable 标记由服务层（services/report_service.py）按 §3.2 判定后填充。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.resource import ResourceRead


# ---------- 新建项目 ----------

class ReportProjectCreatePhase(BaseModel):
    """新建项目弹窗的阶段行（§5.1：类型下拉/计划起止/负责人多选）。"""

    phase_type: str
    plan_start: date | None = None
    plan_end: date | None = None
    assignee_ids: list[int] = []


class ReportProjectCreate(BaseModel):
    """新建项目（§九-2：reporter/admin/manager 可建，managed_by 缺省=当前用户）。

    code 可选（用户 2026-10-29：编号不重要可不填）：留空/缺省 → 后端自动纯数字递增。
    """

    code: str | None = None  # 留空 → next_code 自动生成
    category: str  # 新需求/量产升级/改造（三选一）
    name: str
    market: str
    status: str = "未开始"
    remark: str | None = None
    managed_by: int | None = None  # 项目负责人（缺省=当前用户）
    phases: list[ReportProjectCreatePhase] = []


# ---------- 项目列表 / 详情 ----------

class ReportProjectItem(BaseModel):
    """Tab1 项目卡片行（编号/名称/类目/负责人/市场/状态/进度 + 我的标记）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    owner: str
    market: str
    status: str
    remark: str | None = None
    managed_by: int | None = None
    managed_by_name: str | None = None
    progress: int | None = None  # 名下阶段 progress 均值；无阶段 → None（前端显示"—"）
    is_mine: bool = False  # managed_by == 当前用户
    involved: bool = False  # 我（resource）参与该项目某阶段
    phase_count: int = 0
    overdue: bool = False  # 用户 2026-10-30 指令：名下存在已逾期活跃阶段（与看板同口径）
    due_soon: bool = False  # 名下存在 7 天内到期活跃阶段（项目级标识，阶段口径对齐看板 T4"延期项目"——含"延期"状态，见 report_service.project_overdue_flags）


class ReportPhaseOut(BaseModel):
    """阶段明细行 + 字段级 editable 标记（§六 GET projects/{id}）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    phase_type: str
    name: str
    sequence: int
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    status: str
    progress: int
    remark: str | None = None
    assignees: list[ResourceRead] = []
    assignee_ids: list[int] = []
    editable: dict[str, bool] = {}
    can_request_change: bool = False  # 阶段负责人可对计划时间发起改期申请
    has_pending: bool = False  # 已有待审批的改期申请


class ReportProjectDetail(BaseModel):
    """项目详情（项目级字段 + editable 标记 + 阶段明细）。"""

    id: int
    code: str
    name: str
    category: str
    owner: str
    market: str
    status: str
    remark: str | None = None
    managed_by: int | None = None
    managed_by_name: str | None = None
    is_mine: bool
    # 删除权限（用户 2026-10-29 需求 3）：仅项目负责人及管理员（is_project_owner 含 admin 短路）
    can_delete: bool = False
    editable: dict[str, bool]
    phases: list[ReportPhaseOut] = []


# ---------- 阶段字段级更新 ----------

class ReportPhasePatch(BaseModel):
    """阶段字段级更新（§六 PATCH：越权字段整请求 403 附字段名）。

    负责人直改面含 name/phase_type/sequence（评审 #69：editable map 对 owner
    广播 true，schema 此前不含 → 契约不一致；owner 直改这些字段 422）。
    """

    model_config = ConfigDict(extra="forbid")

    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    status: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    remark: str | None = None
    name: str | None = None  # 负责人直改（名称；与类型互斥时类型自动跟随见 service）
    phase_type: str | None = None  # 负责人直改（类型；名称自动跟随类型显示名）
    sequence: int | None = Field(default=None, ge=1)  # 负责人直改（落库后重排连续）
    assignee_ids: list[int] | None = None  # 提供则整体替换阶段负责人


# ---------- 改期申请 ----------

class ReportChangeRequestCreate(BaseModel):
    """提交变更申请（old 值由服务端从 Phase 现值捕获，§四 JSON 格式）。

    用户 2026-10-29 权限分级需求 4 泛化：除计划时间外，参与者点击修改阶段名称/
    类型/顺序/阶段负责人也触发审核（负责人审批后生效）。None = 该字段不变。
    """

    phase_id: int
    plan_start: date | None = None  # None = 该字段不变
    plan_end: date | None = None
    name: str | None = None
    phase_type: str | None = None
    sequence: int | None = None
    assignee_ids: list[int] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "ReportChangeRequestCreate":
        if (
            self.plan_start is None
            and self.plan_end is None
            and self.name is None
            and self.phase_type is None
            and self.sequence is None
            and self.assignee_ids is None
        ):
            raise ValueError("至少填写一个申请变更的字段")
        return self


class ReportChangeRequestItem(BaseModel):
    """改期申请行（Tab2 待我审批列表 / 提交与审批返回）。"""

    id: int
    phase_id: int
    phase_name: str | None = None
    project_id: int
    project_name: str | None = None
    project_code: str | None = None
    requester_name: str | None = None
    proposed: dict[str, Any] = {}  # {"plan_start": {"old","new"}, "plan_end": {...}}
    status: str
    review_comment: str | None = None
    created_at: datetime | None = None


class ReportChangeReview(BaseModel):
    """审批改期申请（§四：驳回原因必填）。"""

    approved: bool
    comment: str | None = None


# ---------- 元数据 ----------

class ReportMeta(BaseModel):
    """填报页下拉数据（§六 /meta：枚举 + 选人 + 编号预览）。"""

    categories: list[str]
    markets: list[str]
    project_statuses: list[str]
    phase_statuses: list[str]
    phase_types: list[dict[str, str]]  # [{"value": "P1", "label": "需求评估"}, ...]
    users: list[dict[str, Any]]  # 项目负责人候选（在职用户）
    resources: list[dict[str, Any]]  # 阶段负责人候选（资源人员）
    next_code: str  # 编号自动预览（只读）
