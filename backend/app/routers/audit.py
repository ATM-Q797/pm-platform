"""删除审核 + 操作日志 API（Phase 5.3）。

- POST /api/projects/{id}/delete-request  负责人申请删除
- GET  /api/delete-requests               管理员查看申请列表
- POST /api/delete-requests/{id}/review   管理员审核（通过/拒绝）
- GET  /api/operation-logs                查看操作日志
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role, check_project_access
from app.database import get_db
from app.models import OperationLog, Phase, PhaseChangeRequest, Project, ProjectDeleteRequest, User
from app.schemas import (
    DeleteRequestCreate,
    DeleteRequestRead,
    DeleteReview,
    OperationLogRead,
    PhaseChangeRequestCreate,
    PhaseChangeRequestRead,
    PhaseChangeReview,
)

router = APIRouter(tags=["审核与日志"])


# ---------- 操作日志辅助函数 ----------

def log_operation(
    db: Session,
    user: User,
    action: str,
    target_type: str,
    target_id: int | None = None,
    target_name: str | None = None,
    detail: str | None = None,
) -> None:
    """记录一条操作日志（不在此处 commit，由调用方统一提交）。"""
    db.add(OperationLog(
        user_id=user.id,
        user_name=user.name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        detail=detail,
    ))


# ---------- 删除申请 ----------

@router.post(
    "/api/projects/{project_id}/delete-request",
    response_model=DeleteRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def request_delete_project(
    project_id: int,
    payload: DeleteRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """项目负责人申请删除项目（管理员可直接删除，不走申请）。

    - manager 只能申请删除自己负责的项目
    - admin 调此接口也会创建申请（如果想走流程），但通常 admin 直接 DELETE
    - 同一项目已有 pending 申请时返回 400
    """
    # 权限：manager 只能操作自己的项目（admin 也可以申请）
    if user.role == "manager":
        check_project_access(project_id, user, db)
    elif user.role not in ("admin", "manager"):
        raise HTTPException(403, "无权申请删除项目")

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")

    # 检查是否已有 pending 申请
    existing = db.scalars(
        select(ProjectDeleteRequest).where(
            ProjectDeleteRequest.project_id == project_id,
            ProjectDeleteRequest.status == "pending",
        )
    ).first()
    if existing:
        raise HTTPException(400, "该项目已有待审核的删除申请")

    req = ProjectDeleteRequest(
        project_id=project_id,
        requested_by=user.id,
        reason=payload.reason,
        status="pending",
    )
    db.add(req)
    db.flush()
    log_operation(db, user, "request_delete_project", "project", project_id, project.name,
                  detail=f"申请删除，原因：{payload.reason or '未填写'}")
    db.commit()
    db.refresh(req)
    return _enrich_request(req, db)


@router.get("/api/delete-requests", response_model=list[DeleteRequestRead])
def list_delete_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
    status_filter: str | None = Query(None, alias="status"),
):
    """管理员查看删除申请列表（默认全部，可按 pending/approved/rejected 筛选）。"""
    stmt = select(ProjectDeleteRequest).order_by(ProjectDeleteRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(ProjectDeleteRequest.status == status_filter)
    reqs = list(db.scalars(stmt))
    return [_enrich_request(r, db) for r in reqs]


@router.post("/api/delete-requests/{req_id}/review", response_model=DeleteRequestRead)
def review_delete_request(
    req_id: int,
    payload: DeleteReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """管理员审核删除申请：通过则真删项目，拒绝则关闭申请。"""
    req = db.get(ProjectDeleteRequest, req_id)
    if req is None:
        raise HTTPException(404, "删除申请不存在")
    if req.status != "pending":
        raise HTTPException(400, f"该申请已处理（当前状态：{req.status}）")

    project = db.get(Project, req.project_id)
    project_name = project.name if project else f"(已删除 #{req.project_id})"

    req.reviewed_by = user.id
    req.review_comment = payload.comment
    req.reviewed_at = datetime.now()

    if payload.approved:
        req.status = "approved"
        # 真正删除项目（级联删除阶段/依赖）
        if project:
            db.delete(project)
        log_operation(db, user, "approve_delete_project", "project", req.project_id, project_name,
                      detail=f"审核通过删除申请 #{req_id}，项目已删除")
    else:
        req.status = "rejected"
        log_operation(db, user, "reject_delete_project", "project", req.project_id, project_name,
                      detail=f"拒绝删除申请 #{req_id}，评论：{payload.comment or '无'}")

    db.commit()
    db.refresh(req)
    return _enrich_request(req, db)


# ---------- 阶段编辑审批 ----------

@router.post(
    "/api/phase-change-requests",
    response_model=PhaseChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_phase_change_request(
    payload: PhaseChangeRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """工程师提交阶段编辑审批。engineer 编辑阶段后不直接保存，而是创建审批请求。"""
    # 获取阶段信息
    phase = db.get(Phase, payload.phase_id)
    if phase is None:
        raise HTTPException(404, "阶段不存在")
    if user.role not in ("engineer",):
        raise HTTPException(403, "仅工程师需要提交审批")

    # 检查是否已有 pending 请求
    existing = db.scalars(
        select(PhaseChangeRequest).where(
            PhaseChangeRequest.phase_id == payload.phase_id,
            PhaseChangeRequest.status == "pending",
        )
    ).first()
    if existing:
        raise HTTPException(400, "该阶段已有待审核的变更申请")

    import json
    req = PhaseChangeRequest(
        phase_id=payload.phase_id,
        project_id=phase.project_id,
        requested_by=user.id,
        proposed_changes=json.dumps(payload.proposed_changes, ensure_ascii=False),
        status="pending",
    )
    db.add(req)
    db.flush()
    log_operation(db, user, "submit_phase_change", "phase", phase.id, phase.name,
                  detail=f"项目#{phase.project_id}，提交编辑审批")
    db.commit()
    db.refresh(req)
    return _enrich_change_request(req, db)


@router.get("/api/phase-change-requests", response_model=list[PhaseChangeRequestRead])
def list_phase_change_requests(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: str | None = Query(None, alias="status"),
):
    """查看阶段变更审批列表。
    - admin/manager：看所有 pending 请求
    - engineer：看自己提交的
    """
    stmt = select(PhaseChangeRequest).order_by(PhaseChangeRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(PhaseChangeRequest.status == status_filter)
    if user.role in ("engineer",):
        stmt = stmt.where(PhaseChangeRequest.requested_by == user.id)
    reqs = list(db.scalars(stmt))
    return [_enrich_change_request(r, db) for r in reqs]


@router.post("/api/phase-change-requests/{req_id}/review", response_model=PhaseChangeRequestRead)
def review_phase_change_request(
    req_id: int,
    payload: PhaseChangeReview,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """管理员/负责人审核阶段变更：通过则应用修改，拒绝则关闭。"""
    if user.role not in ("admin", "manager"):
        raise HTTPException(403, "仅管理员和项目负责人可审核")

    req = db.get(PhaseChangeRequest, req_id)
    if req is None:
        raise HTTPException(404, "变更申请不存在")
    if req.status != "pending":
        raise HTTPException(400, f"该申请已处理（当前状态：{req.status}）")

    req.reviewed_by = user.id
    req.review_comment = payload.comment
    req.reviewed_at = datetime.now()

    if payload.approved:
        req.status = "approved"
        # 应用变更到阶段
        phase = db.get(Phase, req.phase_id)
        phase_name = phase.name if phase else ""
        if phase:
            import json
            changes = json.loads(req.proposed_changes) if req.proposed_changes else {}
            assignee_ids = changes.pop("assignee_ids", None)
            for k, v in changes.items():
                setattr(phase, k, v)
            if assignee_ids is not None:
                from app.routers.phases import _sync_assignees
                _sync_assignees(db, phase, assignee_ids)
        log_operation(db, user, "approve_phase_change", "phase", req.phase_id,
                      phase_name, detail=f"通过工程师变更审批 #{req_id}")
    else:
        req.status = "rejected"
        log_operation(db, user, "reject_phase_change", "phase", req.phase_id,
                      detail=f"拒绝变更审批 #{req_id}，评论：{payload.comment or '无'}")

    db.commit()
    db.refresh(req)
    return _enrich_change_request(req, db)


def _enrich_change_request(req: PhaseChangeRequest, db: Session) -> PhaseChangeRequestRead:
    """补充阶段名、项目名、申请人名。"""
    phase = db.get(Phase, req.phase_id)
    project = db.get(Project, req.project_id)
    requester = db.get(User, req.requested_by)
    return PhaseChangeRequestRead(
        id=req.id,
        phase_id=req.phase_id,
        phase_name=phase.name if phase else None,
        project_id=req.project_id,
        project_name=project.name if project else None,
        requested_by=req.requested_by,
        requester_name=requester.name if requester else None,
        proposed_changes=req.proposed_changes,
        status=req.status,
        reviewed_by=req.reviewed_by,
        review_comment=req.review_comment,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
    )


def _enrich_request(req: ProjectDeleteRequest, db: Session) -> DeleteRequestRead:
    """补充项目名、申请人名等关联信息。"""
    project = db.get(Project, req.project_id)
    requester = db.get(User, req.requested_by)
    return DeleteRequestRead(
        id=req.id,
        project_id=req.project_id,
        project_name=project.name if project else None,
        project_code=project.code if project else None,
        requested_by=req.requested_by,
        requester_name=requester.name if requester else None,
        reason=req.reason,
        status=req.status,
        reviewed_by=req.reviewed_by,
        review_comment=req.review_comment,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
    )


# ---------- 操作日志 ----------

@router.get("/api/operation-logs", response_model=list[OperationLogRead])
def list_operation_logs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
    limit: int = Query(50, ge=1, le=500),
):
    """管理员查看操作日志（最近 N 条）。"""
    return list(db.scalars(
        select(OperationLog).order_by(OperationLog.id.desc()).limit(limit)
    ))
