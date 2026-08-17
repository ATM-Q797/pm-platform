"""数据库初始化脚本。

用法：
    python init_db.py

功能：
1. 创建所有表（基于 SQLAlchemy ORM 自动建表）
2. 读取 docs/templates.json，写入 3 套模板种子数据（template / template_phase / template_dependency）
3. 幂等：重复运行会清空旧的模板数据再重写（不影响 project/phase 等业务数据）

注意：本脚本会先删除并重建模板相关表的数据，但不会删除整个数据库文件。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 确保能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402,F401  (注册所有模型)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Template, TemplateDependency, TemplatePhase, User  # noqa: E402
from app.core.security import hash_password  # noqa: E402

# templates.json 路径：兼容本地开发（backend/ 子目录）与 Docker 容器（/app 根目录）
def _find_templates_json() -> Path:
    candidates = [
        # 容器内：工作目录 /app，docs 在 /app/docs
        Path("docs") / "templates.json",
        # 本地开发：backend/init_db.py → 项目根/docs
        Path(__file__).resolve().parent.parent / "docs" / "templates.json",
        # 脚本同级 docs（兜底）
        Path(__file__).resolve().parent / "docs" / "templates.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


_TEMPLATES_JSON = _find_templates_json()


def create_tables() -> None:
    Base.metadata.create_all(engine)
    print("✓ 已创建/确认所有表")


def load_seed_data() -> dict:
    if not _TEMPLATES_JSON.exists():
        raise FileNotFoundError(f"模板种子数据不存在: {_TEMPLATES_JSON}")
    with open(_TEMPLATES_JSON, encoding="utf-8") as f:
        return json.load(f)


def seed_templates(db) -> None:
    """写入 3 套模板（幂等：先按 name 清空旧模板再重写）。"""
    seed = load_seed_data()
    templates_data = seed.get("templates", [])

    n_tpl = n_phase = n_dep = 0
    for tpl_data in templates_data:
        name = tpl_data["name"]
        # 幂等：若已存在同名模板，先删除（级联删 phases/deps）
        existing = db.scalars(select(Template).where(Template.name == name)).first()
        if existing:
            db.delete(existing)
            db.flush()

        tpl = Template(name=name, category=tpl_data["category"], description=tpl_data.get("description"))
        db.add(tpl)
        db.flush()
        n_tpl += 1

        for ph in tpl_data.get("phases", []):
            db.add(
                TemplatePhase(
                    template_id=tpl.id,
                    phase_type=ph["phase_type"],
                    name=ph["name"],
                    sequence=ph["sequence"],
                    default_duration_days=ph.get("default_duration_days", 7),
                    default_assignee_role=ph.get("default_assignee_role"),
                )
            )
            n_phase += 1

        for dep in tpl_data.get("dependencies", []):
            db.add(
                TemplateDependency(
                    template_id=tpl.id,
                    from_phase_type=dep["from"],
                    to_phase_type=dep["to"],
                    from_seq=dep.get("from_seq"),
                    to_seq=dep.get("to_seq"),
                    type=dep.get("type", "FS"),
                    lag_days=dep.get("lag_days", 0),
                )
            )
            n_dep += 1

    db.commit()
    print(f"✓ 模板种子写入完成：{n_tpl} 个模板 / {n_phase} 个阶段 / {n_dep} 条依赖")


def seed_admin(db) -> None:
    """创建超级管理员账户（幂等：已存在则跳过）。"""
    ADMIN_USERNAME = "admin"
    existing = db.scalars(select(User).where(User.username == ADMIN_USERNAME)).first()
    if existing:
        print(f"✓ 管理员账户已存在（{ADMIN_USERNAME}），跳过")
        return
    admin = User(
        username=ADMIN_USERNAME,
        name="超级管理员",
        role="admin",
        password_hash=hash_password("admin123"),
        must_change_password=True,  # 首次登录强制改密
    )
    db.add(admin)
    db.commit()
    print(f"✓ 已创建超级管理员：用户名 {ADMIN_USERNAME} / 初始密码 admin123（首次登录请修改）")


def main() -> None:
    print("=" * 50)
    print("智能终端研发项目管理平台 — 数据库初始化")
    print("=" * 50)
    create_tables()
    db = SessionLocal()
    try:
        seed_templates(db)
        seed_admin(db)
    finally:
        db.close()
    # 摘要
    db = SessionLocal()
    try:
        tpls = list(db.scalars(select(Template)))
        print("\n模板摘要:")
        for t in tpls:
            print(f"  [{t.id}] {t.name} ({t.category}) — {len(t.phases)} 阶段, {len(t.dependencies)} 依赖")
    finally:
        db.close()
    print("\n✅ 初始化完成。启动服务：uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
