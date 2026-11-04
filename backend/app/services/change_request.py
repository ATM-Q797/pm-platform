"""改期申请共享层（二期④，用户 2026-11-04）：直改计划时间 → pending 申请自动作废。

为什么需要这一层：这条规则原本只装在填报页（report_service.check_phase_patch），
而旧入口 routers/phases.py:update_phase 改阶段从不经过它。后果不是「页面不同步」，
而是数据会被回滚——负责人先在旧页面把日期改成 A，挂着的申请仍是 pending，
谁再点一次「批准」，apply_change_proposal 就按申请里的旧提案把日期写回 B。

放 service 层而不是让 phases.py 反向 import report_service：路由层不允许反向依赖，
且 report_service 已经 import 了 phases._sync_assignees（同向依赖）。
本模块只做状态流转，不写审计日志、不发通知——这两件事由调用方在同一事务内完成，
以免 service 反向依赖 routers.audit。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Phase, PhaseChangeRequest, User


def get_pending_request(db: Session, phase_id: int) -> PhaseChangeRequest | None:
    """该阶段当前 pending 的改期申请（单一 pending 语义，audit.py:183-189 同口径）。"""
    return db.scalars(
        select(PhaseChangeRequest).where(
            PhaseChangeRequest.phase_id == phase_id,
            PhaseChangeRequest.status == "pending",
        )
    ).first()


def invalidate_pending_on_direct_edit(
    db: Session, phase: Phase, user: User
) -> PhaseChangeRequest | None:
    """负责人直改计划时间 → 该阶段 pending 申请自动置 rejected。

    返回被作废的申请（无 pending 时 None），调用方据此写审计日志并通知申请人。
    """
    pending = get_pending_request(db, phase.id)
    if pending is None:
        return None
    pending.status = "rejected"
    pending.reviewed_by = user.id
    pending.review_comment = "负责人已直接改期，申请作废"
    pending.reviewed_at = datetime.now()
    return pending
