"""User 的 Pydantic 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    username: str
    name: str
    role: str = "engineer"  # admin/manager/engineer/viewer


class UserCreate(UserBase):
    password: str  # 明文，后端加密
    resource_id: int | None = None  # 关联的资源（可空）


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    resource_id: int | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    must_change_password: bool
    resource_id: int | None = None
    created_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录成功返回的用户信息（token 在 Cookie 里，不在 body）。"""
    user: UserRead
    must_change_password: bool
