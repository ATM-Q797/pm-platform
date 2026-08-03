"""认证 API 路由。

- POST /api/auth/login：校验账号密码，Set-Cookie(httpOnly) 下发 JWT
- POST /api/auth/logout：清除 Cookie
- GET /api/auth/me：返回当前登录用户
- PUT /api/auth/password：修改自己的密码
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import (
    COOKIE_NAME,
    TOKEN_EXPIRE_HOURS,
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, PasswordChange, UserRead

router = APIRouter(prefix="/api/auth", tags=["认证"])

# Cookie 配置：httpOnly（免疫 XSS）+ SameSite=Lax + 24h
_COOKIE_KWARGS = dict(
    key=COOKIE_NAME,
    httponly=True,
    samesite="lax",
    max_age=TOKEN_EXPIRE_HOURS * 3600,
    path="/",
)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """登录：校验账号密码 → 下发 httpOnly Cookie JWT。"""
    user = db.scalars(select(User).where(User.username == payload.username)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账户已禁用，请联系管理员")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie(value=token, **_COOKIE_KWARGS)

    return LoginResponse(
        user=UserRead.model_validate(user),
        must_change_password=user.must_change_password,
    )


@router.post("/logout")
def logout(response: Response):
    """登出：清除 Cookie。"""
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"message": "已登出"}


@router.get("/me", response_model=UserRead)
def get_me(user: User = Depends(get_current_user)):
    """返回当前登录用户。"""
    return user


@router.put("/password")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改自己的密码（首登强制改密也用此接口）。"""
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "原密码错误")
    if len(payload.new_password) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码至少 4 位")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    return {"message": "密码已修改"}
