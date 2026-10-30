"""用户管理 API（仅管理员）。

- GET    /api/users       用户列表
- POST   /api/users       创建用户（自动关联 resource）
- PUT    /api/users/{id}  更新用户（改角色/启用禁用/关联资源）
- DELETE /api/users/{id}  删除用户
- POST   /api/users/{id}/force-delete    强制删除（墓碑式，评审 #3 补日志）
- POST   /api/users/{id}/reset-password  重置密码
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.security import hash_password
from app.database import get_db
from app.models import Resource, User
from app.routers.audit import log_operation
from app.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/api/users", tags=["用户管理"])

# 默认初始密码
DEFAULT_PASSWORD = "123456"


@router.get("", response_model=list[UserRead])
@router.get("/", response_model=list[UserRead], include_in_schema=False)
def list_users(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    return list(db.scalars(select(User).where(User.force_deleted_at.is_(None)).order_by(User.id)))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    # 用户名唯一
    if db.scalars(select(User).where(User.username == payload.username)).first():
        raise HTTPException(400, f"用户名 {payload.username} 已存在")

    # 若指定 resource_id，校验存在且未被其他用户关联
    resource_id = payload.resource_id
    if resource_id is not None:
        res = db.get(Resource, resource_id)
        if res is None:
            raise HTTPException(400, f"资源 id {resource_id} 不存在")
        # 检查是否已被关联
        existing = db.scalars(select(User).where(User.resource_id == resource_id)).first()
        if existing:
            raise HTTPException(400, f"资源 {res.name} 已关联用户 {existing.username}")

    user = User(
        username=payload.username,
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password or DEFAULT_PASSWORD),
        resource_id=resource_id,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_live_user(db: Session, user_id: int) -> User:
    """取未墓碑用户（评审 #2）：强制删除用户只读——更新/重置密码/物理删除一律拒绝，
    防止 PUT is_active=true 复活登录能力（弹窗承诺"无法登录"的唯一保障）。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    if user.force_deleted_at is not None:
        raise HTTPException(404, "用户不存在（已强制删除）")
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    user = _get_live_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "resource_id" in data and data["resource_id"] is not None:
        existing = db.scalars(
            select(User).where(User.resource_id == data["resource_id"], User.id != user_id)
        ).first()
        if existing:
            raise HTTPException(400, "该资源已被其他用户关联")
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_role("admin")),
):
    if user_id == current.id:
        raise HTTPException(400, "不能删除自己")
    user = _get_live_user(db, user_id)
    try:
        db.delete(user)
        db.commit()
    except IntegrityError:
        # 审计完整性保护（用户 2026-10-29 裁定）：操作日志保留谁做过什么，
        # 有日志引用的账号不允许物理删除——引导停用/强制删除而非删除
        db.rollback()
        raise HTTPException(
            400,
            "该账号有操作记录，不能直接删除（审计日志须永久保留）——"
            "如需清除请连续点击删除 4 次后走「强制删除」，或改用「停用」",
        )


@router.post("/{user_id}/force-delete", status_code=status.HTTP_204_NO_CONTENT)
def force_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_role("admin")),
):
    """强制删除（墓碑式，用户 2026-10-29 指令）：打 force_deleted_at 标记，不物理删除——
    操作日志/项目负责人指派等外键引用无损保留，日志侧显示“（已强制删除）”后缀；
    该用户从列表消失、无法登录。"""
    if user_id == current.id:
        raise HTTPException(400, "不能强制删除自己")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    if user.force_deleted_at is not None:
        raise HTTPException(400, "该用户已是强制删除状态")
    user.force_deleted_at = datetime.now()
    user.is_active = False  # 双保险：墓碑用户不可登录
    # 评审 #3：强制删除动作本身必须留痕（哪个管理员在何时强制删除了谁）——
    # 该功能的立足点就是审计完整性，行为不可追溯与立足点相悖
    log_operation(db, current, "force_delete_user", "user", user.id, user.name,
                  detail=f"强制删除用户「{user.name}」（{user.username}）——墓碑式，操作日志保留")
    db.commit()


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    user = _get_live_user(db, user_id)  # 评审 #2：墓碑用户只读（含重置密码）
    user.password_hash = hash_password(DEFAULT_PASSWORD)
    user.must_change_password = True
    db.commit()
    return {"message": f"密码已重置为 {DEFAULT_PASSWORD}"}
