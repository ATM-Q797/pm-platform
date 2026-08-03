"""FastAPI 应用入口。

- 挂载所有路由
- 配置 CORS（允许前端 http://localhost:5173）
- 启动时确保导入所有模型
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (注册 ORM 模型)
from app.routers import dependencies, exports, imports, phases, projects, resources, templates, dashboard

app = FastAPI(
    title="智能终端研发项目管理平台 API",
    description="硬件研发项目管理平台后端 — 项目规格见 docs/PROJECT_SPEC.md",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (projects, phases, dependencies, resources, templates, imports, exports, dashboard):
    app.include_router(r.router)


@app.get("/", tags=["健康检查"])
def root():
    return {"status": "ok", "service": "pm-platform-api", "docs": "/docs"}
