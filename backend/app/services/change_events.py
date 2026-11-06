"""过程事件服务（P1 过程事件地基，PHASE8_PLAN §九 方案 B）。

- 白名单 8+1 字段：计划时间/状态/进度/负责人/实际时间/返工计数；
  is_special 用户裁定不入（权限管理维度，非过程数据）。
- 来源枚举：direct_edit（详情页直改）/ report_edit（填报页改）/ approval（审批批准）/ rework（返工）。
- 原值新值 TEXT 直存（白名单全是标量：date isoformat / int / str）。
- 记录函数不 commit——与 log_operation 同模式，由调用方统一提交。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import DataChangeEvent
from app.models.phase import Phase
from app.models.project import Project
from app.models.user import User

# 白名单：项目级 + 阶段级字段（field 名 → 中文名）
FIELD_LABELS: dict[str, str] = {
    "code": "项目编号",
    "name": "项目名称",
    "owner": "项目客户负责人",
    "market": "市场区域",
    "status": "项目状态",
    "priority": "优先级",
    "plan_start": "项目计划开始",
    "plan_end": "项目计划结束",
    "managed_by": "项目负责人",
    "phase_plan_start": "阶段计划开始",
    "phase_plan_end": "阶段计划结束",
    "actual_start": "阶段实际开始",
    "actual_end": "阶段实际完成",
    "phase_status": "阶段状态",
    "progress": "进度",
    "rework_count": "返工次数",
    "phase_type": "阶段类型",
}

# 阶段白名单字段在 Phase 模型上的真实列名（phase_ 前缀仅用于区分项目级同名 field）
PHASE_FIELD_COLUMNS: dict[str, str] = {
    "phase_plan_start": "plan_start",
    "phase_plan_end": "plan_end",
    "actual_start": "actual_start",
    "actual_end": "actual_end",
    "phase_status": "status",
    "progress": "progress",
    "rework_count": "rework_count",
    "phase_type": "phase_type",
}

PROJECT_FIELD_COLUMNS: dict[str, str] = {
    "code": "code",
    "name": "name",
    "owner": "owner",
    "market": "market",
    "status": "status",
    "priority": "priority",
    "plan_start": "plan_start",
    "plan_end": "plan_end",
    "managed_by": "managed_by",
}

SOURCES = ("direct_edit", "report_edit", "approval", "rework")

# 审批提案字段名（proposed_changes key）→ 事件 field 名映射。
# 提案里 name/assignee_ids/sequence 属非白名单（§9.3：审计只捕过程数据字段），不入映射。
PHASE_PROPOSAL_FIELD_MAP: dict[str, str] = {
    "plan_start": "phase_plan_start",
    "plan_end": "phase_plan_end",
    "phase_type": "phase_type",
}


def _serialize(v: Any) -> str | None:
    """标量序列化：date → isoformat；其余 → str；None 保持 None（= 置空）。"""
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def record_change_event(
    db: Session,
    *,
    user: User | None,
    field: str,
    old: Any,
    new: Any,
    source: str,
    project_id: int | None = None,
    phase_id: int | None = None,
    project_name: str | None = None,
    phase_name: str | None = None,
    reason: str | None = None,
) -> None:
    """记录一条过程事件（不 commit，由调用方统一提交）。

    old/new 在调用前先取现值再 setattr——本函数不做 diff，只负责落行。
    """
    if source not in SOURCES:
        raise ValueError(f"非法 source：{source}（合法：{SOURCES}）")
    if field not in FIELD_LABELS:
        raise ValueError(f"非白名单字段：{field}")
    db.add(DataChangeEvent(
        project_id=project_id,
        phase_id=phase_id,
        field=field,
        old_value=_serialize(old),
        new_value=_serialize(new),
        source=source,
        changed_by=user.id if user else None,
        changed_by_name=user.name if user else None,
        project_name=project_name,
        phase_name=phase_name,
        reason=reason,
    ))


def record_field_diffs(
    db: Session,
    *,
    user: User | None,
    before: dict[str, Any],
    after: dict[str, Any],
    columns: dict[str, str],
    source: str,
    project_id: int | None = None,
    phase_id: int | None = None,
    project_name: str | None = None,
    phase_name: str | None = None,
) -> int:
    """对 before/after diff 命中白名单的字段逐条记事件，返回条数。

    columns：field 名 → 模型列名映射（PROJECT_FIELD_COLUMNS / PHASE_FIELD_COLUMNS）。
    before/after 的 key 用模型列名（与 update_project/update_phase 的 data dict 同形）。
    """
    n = 0
    for field, col in columns.items():
        if col not in before and col not in after:
            continue
        old = before.get(col)
        new = after.get(col)
        if old != new:
            record_change_event(
                db, user=user, field=field, old=old, new=new, source=source,
                project_id=project_id, phase_id=phase_id,
                project_name=project_name, phase_name=phase_name,
            )
            n += 1
    return n


def snapshot_model(obj: Project | Phase, columns: dict[str, str]) -> dict[str, Any]:
    """按 columns 取模型现值快照（setattr 前调用，作为 before）。"""
    return {col: getattr(obj, col) for col in columns.values()}
