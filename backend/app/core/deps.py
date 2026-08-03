"""认证与权限依赖。

FastAPI Dependency，三层粒度：
1. get_current_user — 要求登录（任何认证用户）
2. require_role — 要求特定角色
3. require_project_access / require_phase_access — 资源所有权
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


def require_project_access(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """要求项目访问权：管理员或该项目负责人。"""
    if user.role == "admin":
        return user
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    # manager 只能访问自己负责的项目
    if user.role == "manager":
        if project.managed_by != user.id and project.owner != user.name:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此项目")
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作项目")


def require_phase_access(
    phase_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """要求阶段访问权：管理员/项目负责人/该阶段分配的工程师。"""
    if user.role == "admin":
        return user
    phase = db.get(Phase, phase_id)
    if phase is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "阶段不存在")
    # 工程师：只能改分配给自己的阶段
    if user.role == "engineer":
        assignee_ids = {r.id for r in phase.assignees}
        if user.resource_id and user.resource_id in assignee_ids:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此阶段")
    # manager：检查是否负责该阶段所属项目
    if user.role == "manager":
        project = db.get(Project, phase.project_id)
        if project and (project.managed_by == user.id or project.owner == user.name):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此项目阶段")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
