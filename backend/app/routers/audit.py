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
from app.models import OperationLog, Project, ProjectDeleteRequest, User
from app.schemas import DeleteRequestCreate, DeleteRequestRead, DeleteReview, OperationLogRead

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
