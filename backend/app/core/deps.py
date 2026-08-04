"""认证与权限依赖。

FastAPI Dependency，三层粒度：
1. get_current_user — 要求登录（任何认证用户）
2. require_role — 要求特定角色
3. check_project_access / check_phase_access — 手动调用的资源所有权检查
   以及对应的 Depends 包装：require_project_access / require_phase_access
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import COOKIE_NAME, decode_access_token
from app.database import get_db
from app.models import Phase, Project, User


def get_current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """要求登录：从 Cookie 读 JWT，返回当前用户。未登录 401。"""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效的登录凭证")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return user


def require_role(*roles: str):
    """要求特定角色。用法：Depends(require_role("admin", "manager"))"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"需要角色: {', '.join(roles)}")
        return user

    return checker


# ---------- 纯检查函数（供端点内手动调用）----------

def check_project_access(project_id: int, user: User, db: Session) -> Project:
    """检查项目访问权（不依赖 Depends，直接调用）。无权限时抛 403/404。"""
    if user.role == "admin":
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
        return project
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    if user.role == "manager":
        # manager 只能访问 managed_by 指向自己的项目
        # 兼容历史数据：managed_by 为空时回退到 owner 文本匹配（导入的旧数据）
        if project.managed_by == user.id:
            return project
        if project.managed_by is None and project.owner == user.name:
            return project
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此项目")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作项目")


def check_phase_access(phase_id: int, user: User, db: Session) -> Phase:
    """检查阶段访问权（不依赖 Depends，直接调用）。无权限时抛 403。"""
    if user.role == "admin":
        phase = db.get(Phase, phase_id)
        if phase is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "阶段不存在")
        return phase
    phase = db.get(Phase, phase_id)
    if phase is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "阶段不存在")
    # 工程师：只能改分配给自己的阶段
    if user.role == "engineer":
        assignee_ids = {r.id for r in phase.assignees}
        if user.resource_id and user.resource_id in assignee_ids:
            return phase
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此阶段")
    # manager：检查是否负责该阶段所属项目（managed_by 优先，兼容 owner 文本）
    if user.role == "manager":
        project = db.get(Project, phase.project_id)
        if project:
            if project.managed_by == user.id:
                return phase
            if project.managed_by is None and project.owner == user.name:
                return phase
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此项目阶段")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")


# ---------- Depends 包装器（用于 FastAPI 依赖注入，仅可当 Depends 使用）----------

def require_project_access(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """要求项目访问权：管理员或该项目负责人。用 check_project_access。"""
    check_project_access(project_id, user, db)
    return user


def require_phase_access(
    phase_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """要求阶段访问权：管理员/项目负责人/该阶段分配的工程师。"""
    check_phase_access(phase_id, user, db)
    return user
