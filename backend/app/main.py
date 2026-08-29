"""FastAPI 应用入口。
	
- 挂载所有路由
- 配置 CORS（通过环境变量 CORS_ORIGINS 控制，开发默认 localhost）
- 启动时确保导入所有模型
- 启动时校验生产环境安全配置
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
load_dotenv()  # 加载 backend/.env（本地开发免手动设环境变量）

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (注册 ORM 模型)
from app.core.logging import setup_logging
from app.core.security import APP_ENV, SECRET_KEY, _DEV_FALLBACK_SECRET
from app.routers import (
    audit,
    auth,
    dashboard,
    dependencies,
    exports,
    imports,
    phases,
    projects,
    resources,
    templates,
    users,
)

logger = logging.getLogger(__name__)

# 初始化日志
setup_logging()

app = FastAPI(
    title="智能终端研发项目管理平台 API",
    description="硬件研发项目管理平台后端 — 项目规格见 docs/PROJECT_SPEC.md",
    version="0.3.0",
)

# ---------------------------------------------------------------------------
# CORS 配置
# - 生产环境：通过 CORS_ORIGINS 环境变量设置（逗号分隔），如:
#     CORS_ORIGINS=https://pm.example.com,https://www.pm.example.com
# - 开发环境：默认允许 localhost 常用端口
# ---------------------------------------------------------------------------
_CORS_ORIGINS_ENV = os.environ.get("CORS_ORIGINS", "")
if _CORS_ORIGINS_ENV:
    _allow_origins = [o.strip() for o in _CORS_ORIGINS_ENV.split(",") if o.strip()]
else:
    _allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,  # 允许携带 Cookie（认证必需）
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 禁缓存中间件（消除冲突后黄框滞留排查结论，2026-08-30）：
# GET /api/* 响应不带 Cache-Control 时，Chrome 走启发式缓存——消除冲突后前端重拉
# /conflicts 命中旧响应，界面看不到变化（刷新页面才绕过缓存）。API 数据一律 no-store;
# 前端静态资源不受影响（vite/nginx 自行管理）。
# ---------------------------------------------------------------------------
@app.middleware("http")
async def _no_cache_for_api(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


for r in (auth, users, audit, projects, phases, dependencies, resources, templates, imports, exports, dashboard):
    app.include_router(r.router)


# ---------------------------------------------------------------------------
# 启动时安全校验
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup_security_check():
    """生产环境启动前校验关键安全配置。"""
    if APP_ENV == "production":
        if SECRET_KEY == _DEV_FALLBACK_SECRET or len(SECRET_KEY) < 32:
            raise RuntimeError(
                "生产环境必须设置安全的 JWT_SECRET_KEY（至少32字符）。"
                "生成方式: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        logger.info("生产环境安全检查通过 (APP_ENV=production)")
    else:
        logger.info("开发模式启动 (APP_ENV=development)")


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@app.get("/", tags=["健康检查"])
def root():
    return {"status": "ok", "service": "pm-platform-api", "docs": "/docs"}


@app.get("/health", tags=["健康检查"])
def health():
    """深度健康检查：验证 DB 连接是否正常。"""
    from app.database import engine
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    overall = "ok" if db_status == "ok" else "degraded"
    return {
        "status": overall,
        "service": "pm-platform-api",
        "env": APP_ENV,
        "database": db_status,
    }
