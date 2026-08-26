"""数据库迁移 v2 — Phase 6 引入的结构变更（幂等，可重复执行）。

变更内容（相对 2026-08-17 部署版本）：
1. phase 表新增 updated_at 列（T7 周报遗留字段，保留用于时间追踪）
2. 新建 user_favorite 表（关注项目置顶）

用法（服务器容器内）：
    docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env \
      exec -T backend python migrate_v2.py

说明：
- 不删除任何现有数据，只做"加列/建表"
- ALTER ... IF NOT EXISTS 与 create_all 均幂等，可放心重复执行
"""
from __future__ import annotations

from sqlalchemy import text

from app import models  # noqa: F401  (注册所有模型)
from app.database import Base, engine


def main() -> None:
    # 1. phase.updated_at 列（旧表手工补列；DEFAULT 与模型 server_default 一致）
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE phase ADD COLUMN IF NOT EXISTS updated_at "
            "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ))
        print("✓ phase.updated_at 列已确认")

    # 2. 缺失的表（user_favorite 等）自动创建
    Base.metadata.create_all(engine)
    print("✓ 缺失表已创建（user_favorite 等）")

    print("数据库迁移完成（数据未改动）")


if __name__ == "__main__":
    main()
