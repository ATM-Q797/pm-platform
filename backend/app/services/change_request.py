"""改期申请共享层（二期④，用户 2026-11-04）：直改计划时间 → pending 申请自动作废。

为什么需要这一层：这条规则原本只装在填报页（report_service.check_phase_patch），
而旧入口 routers/phases.py:update_phase 改阶段从不经过它。后果不是「页面不同步」，
而是数据会被回滚——负责人先在旧页面把日期改成 A，挂着的申请仍是 pending，
谁再点一次「批准」，apply_change_proposal 就按申请里的旧提案把日期写回 B。

放 service 层而不是让 phases.py 反向 import report_service：路由层不允许反向依赖，
且 report_service 已经 import 了 phases._sync_assignees（同向依赖）。
本模块只做状态流转与判定，不写审计日志、不发通知——这两件事由调用方在同一事务内完成，
以免 service 反向依赖 routers.audit。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Phase, PhaseChangeRequest, User

# 作废时写入的驳回原因。既是给用户看的说明，也是「这是自动作废、不是人工驳回」的
# 结构标记（出参 invalidated 由它派生）——前端不再自己匹配中文文案。
INVALIDATION_COMMENT = "负责人已直接改期，申请作废"


def get_pending_request(db: Session, phase_id: int) -> PhaseChangeRequest | None:
    """该阶段当前 pending 的改期申请（单一 pending 语义，audit.py:183-189 同口径）。"""
    return db.scalars(
        select(PhaseChangeRequest).where(
            PhaseChangeRequest.phase_id == phase_id,
            PhaseChangeRequest.status == "pending",
        )
    ).first()


def plan_fields_really_changed(phase: Phase, data: dict) -> bool:
    """请求里带的计划字段是否**真的**改了值（不是"字段出现在 payload 里"）。

    为什么必须按值比较：旧入口的表单每次保存都会带上 plan_start/plan_end
    （PhaseEditor 无条件写入 payload），若按"字段是否出现"判定，
    负责人只改进度/状态也会误废申请人的待审申请，并发出不实通知。
    """
    fields = {"plan_start", "plan_end"} & set(data)
    return any(data[f] != getattr(phase, f) for f in fields)


def invalidate_pending_on_direct_edit(
    db: Session, phase: Phase, user: User
) -> list[PhaseChangeRequest]:
    """负责人直改计划时间 → 该阶段**全部** pending 申请置 rejected。

    为什么收敛全部而不是第一条：单 pending 只是应用层检查，DB 无唯一约束；
    历史重复行或并发写入一旦存在，只清一条会留下第二条，它被批准时照样把日期写回旧提案。
    返回被作废的申请列表（无 pending 时为空），调用方据此写审计日志并通知申请人。
    """
    rows = list(db.scalars(
        select(PhaseChangeRequest).where(
            PhaseChangeRequest.phase_id == phase.id,
            PhaseChangeRequest.status == "pending",
        )
    ).all())
    if not rows:
        return []
    now = datetime.now()
    for row in rows:
        row.status = "rejected"
        row.reviewed_by = user.id
        row.review_comment = INVALIDATION_COMMENT
        row.reviewed_at = now
    return rows
