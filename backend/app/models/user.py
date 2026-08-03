"""user（用户）模型。

对应 PHASE5_PLAN §2.1。用户登录账户，与 resource 一一对应。
- admin/manager/engineer/viewer 四种角色
- bcrypt 加密密码
- is_active 控制启用/禁用
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.resource import Resource


class User(Base):
    __tablename__ = "user_account"  # user 是 PG 保留字，用 user_account 避免冲突

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)  # 显示名（真实姓名）
    role: Mapped[str] = mapped_column(String, nullable=False, default="engineer", server_default="engineer")
    # admin/manager/engineer/viewer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )  # 初始密码，首次登录强制改
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # 关联的 resource（一一对应，可空——管理员可能不对应具体资源）
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resource.id"))
    resource: Mapped["Resource | None"] = relationship(back_populates="user")
