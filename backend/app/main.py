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
from app.models import User
from app.routers import (
    analysis,
    audit,
    auth,
    dashboard,
    dependencies,
    exports,
    imports,
    phases,
    projects,
    report,
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


for r in (auth, users, audit, projects, phases, dependencies, resources, templates, imports, exports, dashboard, analysis, report):
    app.include_router(r.router)


# ---------------------------------------------------------------------------
# reporter（填报人）API 封锁门（信息填报一期 §3.1）
# 设计预期靠 require_role 白名单默认拒绝，实测既有接口多为仅登录（get_current_user）
# 或无鉴权（resources/dashboard/templates 只读面），reporter 可穿透——故在应用层
# 统一设门：reporter 登录态访问 /api/* 一律 403，白名单仅放行 /api/report/* 与
# /api/auth/*（登录/登出/改密）。旧路由零改动；封锁面由 test_report_auth.py 矩阵核验。
# ---------------------------------------------------------------------------
_REPORT_ALLOWED_PREFIXES = ("/api/report", "/api/auth")


@app.middleware("http")
async def _reporter_lockdown(request, call_next):
    path = request.url.path
    if path.startswith("/api") and not any(path.startswith(p) for p in _REPORT_ALLOWED_PREFIXES):
        # 仅查登录身份（token 在 Cookie），未登录交给原路由的鉴权逻辑
        from app.core.security import COOKIE_NAME, decode_access_token
        token = request.cookies.get(COOKIE_NAME)
        payload = decode_access_token(token) if token else None
        if payload is not None:
            try:
                sub = int(payload.get("sub"))
            except (TypeError, ValueError):
                sub = None
            if sub is not None:
                # 沿用请求级会话：优先测试 override 的 get_db，否则默认 SessionLocal
                from app.database import SessionLocal, get_db
                override = request.app.dependency_overrides.get(get_db)
                db = override() if override else SessionLocal()
                session = next(db) if override else db
                try:
                    user = session.get(User, sub)
                    if user is not None and user.is_active and user.role == "reporter":
                        from fastapi.responses import JSONResponse
                        return JSONResponse(status_code=403, content={"detail": "填报人仅可访问信息填报接口"})
                finally:
                    if override:
                        try:
                            next(db)
                        except StopIteration:
                            pass
                    else:
                        session.close()
    return await call_next(request)


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
