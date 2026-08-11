"""项目相关 API 路由。

对应 PROJECT_SPEC §4.2 项目端点。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role, check_project_access
from app.database import get_db
from app.models import Dependency, Phase, Project, User, phase_assignee
from app.routers.audit import log_operation
from app.schemas import (
    GanttData,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)
from app.services import apply_template, build_gantt

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.get("", response_model=list[ProjectRead])
@router.get("/", response_model=list[ProjectRead], include_in_schema=False)
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_: str | None = Query(None, alias="status"),
    category: str | None = None,
    market: str | None = None,
):
    """项目列表，支持筛选。按角色过滤可见范围：
    - admin / viewer：看全部项目
    - manager：看自己创建的项目 + 自己参与的项目（resource 被分配了阶段的）
    - engineer：只看自己参与的项目
    """
    if user.role in ("admin", "viewer"):
        stmt = select(Project)
    else:
        # manager / engineer：过滤可见项目
        stmt = select(Project)
        if user.role == "manager":
            # 自己创建的 或 自己参与的
            conditions = [Project.created_by == user.id]
        else:
            conditions = []
        # 自己参与的：resource 被分配到该项目的某个阶段
        if user.resource_id:
            conditions.append(
                Project.id.in_(
                    select(Phase.project_id).join(
                        phase_assignee, Phase.id == phase_assignee.c.phase_id
                    ).where(phase_assignee.c.resource_id == user.resource_id)
                )
            )
        if not conditions:
            # 工程师没关联 resource 时返回空列表
            return []
        stmt = stmt.where(or_(*conditions))

    if status_:
        stmt = stmt.where(Project.status == status_)
    if category:
        stmt = stmt.where(Project.category == category)
    if market:
        stmt = stmt.where(Project.market == market)
    stmt = stmt.order_by(Project.id)
    return list(db.scalars(stmt))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    if db.scalars(select(Project).where(Project.code == payload.code)).first():
        raise HTTPException(400, f"项目编号 {payload.code} 已存在")
    data = payload.model_dump()
    # 自动记录创建者；manager 创建时若未指定 managed_by，默认为自己的 user_id
    data["created_by"] = user.id
    if data.get("managed_by") is None and user.role == "manager":
        data["managed_by"] = user.id
    project = Project(**data)
    db.add(project)
    db.commit()
    db.refresh(project)
    log_operation(db, user, "create_project", "project", project.id, project.name)
    db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    # 附加依赖列表
    deps = db.execute(
        select(Dependency).join(Phase, Dependency.from_phase_id == Phase.id).where(Phase.project_id == project_id)
    ).scalars().all()
    detail = ProjectDetail.model_validate(project)
    detail.dependencies = deps  # type: ignore[assignment]
    return detail


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 检查项目存在 + 操作权限
    project = check_project_access(project_id, user, db)
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != project.code:
        dup = db.scalars(select(Project).where(Project.code == data["code"])).first()
        if dup:
            raise HTTPException(400, f"项目编号 {data['code']} 已存在")
    for k, v in data.items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    log_operation(db, user, "update_project", "project", project.id, project.name,
                  detail=f"修改字段：{', '.join(data.keys())}")
    db.commit()
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除项目。

    - admin：直接物理删除
    - manager：不能直接删，提示走删除申请流程（POST /api/projects/{id}/delete-request）
    """
    project = check_project_access(project_id, user, db)
    if user.role == "manager":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "项目负责人不能直接删除项目，请申请删除（调用 delete-request 接口）",
        )
    # 先记日志再删（删后拿不到项目信息）
    log_operation(db, user, "delete_project", "project", project.id, project.name,
                  detail=f"管理员直接删除项目「{project.name}」")
    db.delete(project)
    db.commit()


@router.get("/{project_id}/gantt", response_model=GanttData)
def get_project_gantt(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目甘特图数据（dhtmlxGantt 格式）。需登录。"""
    data = build_gantt(db, project_id)
    if data is None:
        raise HTTPException(404, "项目不存在")
    return data


@router.post("/{project_id}/apply-template/{template_id}", response_model=ProjectRead)
def apply_template_to_project(
    project_id: int,
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从模板创建阶段 + 依赖。"""
    # 检查项目存在 + 操作权限
    check_project_access(project_id, user, db)
    try:
        apply_template(db, project_id, template_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    db.commit()
    return db.get(Project, project_id)
