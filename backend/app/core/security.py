"""认证安全模块：密码加密 + JWT 生成/验证。

- 密码用 bcrypt 加密（passlib）
- JWT 用 python-jose，HS256 签名
- Token 通过 httpOnly Cookie 下发（见 routers/auth.py）
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# JWT 密钥：生产环境 **必须** 通过环境变量 JWT_SECRET_KEY 设置强随机字符串
#   生成方式: python -c "import secrets; print(secrets.token_urlsafe(48))"
# 开发环境允许使用不安全的默认值；生产环境未设置时启动会报错（见 main.py 的 startup check）
# ---------------------------------------------------------------------------
_DEV_FALLBACK_SECRET = "pm-platform-dev-secret-change-in-production-2026"
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", _DEV_FALLBACK_SECRET)
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.environ.get("TOKEN_EXPIRE_HOURS", "24"))

# 运行模式：production | development（默认 development）
APP_ENV = os.environ.get("APP_ENV", "development")

# bcrypt 密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Cookie 名称
COOKIE_NAME = "pm_token"


def hash_password(password: str) -> str:
    """加密密码。"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。"""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict[str, Any]) -> str:
    """生成 JWT。data 里应含 sub（用户 id）。"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 JWT，失败返回 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
