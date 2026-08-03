"""数据迁移脚本：SQLite → PostgreSQL。

用法（确保 PG 已启动、pm_platform 库已建、表已用 init_db.py 创建）：
    python migrate_to_pg.py

功能：
1. 从 backend/pm_platform.db（SQLite）读取所有业务数据
2. 写入 PostgreSQL（DATABASE_URL 默认 postgresql://postgres@localhost:5432/pm_platform）
3. 迁移前清空 PG 目标表（避免重复），迁移后校验行数一致

注意：先在 PG 上跑 init_db.py 建表（含模板），再跑本脚本迁移业务数据。
本脚本只迁移 project/phase/dependency/resource/phase_assignee/rework_log，
不迁移 template 系列（init_db.py 已写入）。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, select, text  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import Base, DATABASE_URL  # noqa: E402
from app.models import (  # noqa: E402
    Dependency,
    Phase,
    Project,
    Resource,
    ReworkLog,
    phase_assignee,
)

# SQLite 源文件
_SQLITE_PATH = Path(__file__).resolve().parent / "pm_platform.db"

# 需迁移的业务表（不含 template 系列，init_db.py 已处理）
# 按依赖顺序（被依赖的先迁）
_TABLES_ORDER = ["resource", "project", "phase", "phase_assignee", "dependency", "rework_log"]


def read_sqlite_rows(table: str) -> list[dict]:
    """从 SQLite 读一张表的所有行，返回 dict 列表。"""
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    conn.close()
    return rows


def main() -> None:
    if not _SQLITE_PATH.exists():
        print(f"✗ SQLite 文件不存在: {_SQLITE_PATH}")
        sys.exit(1)

    print("=" * 50)
    print("数据迁移：SQLite → PostgreSQL")
    print("=" * 50)
    print(f"源: {_SQLITE_PATH}")
    print(f"目标: {DATABASE_URL}")

    # 读 SQLite 数据
    sqlite_data: dict[str, list[dict]] = {}
    for t in _TABLES_ORDER:
        sqlite_data[t] = read_sqlite_rows(t)
        print(f"  读 {t}: {len(sqlite_data[t])} 行")

    # 连 PG
    engine = create_engine(DATABASE_URL, future=True)

    # 清空 PG 目标表（按反向依赖顺序删，避免外键约束）
    with engine.connect() as conn:
        for t in reversed(_TABLES_ORDER):
            conn.execute(text(f"DELETE FROM {t}"))
        conn.commit()
    print("  已清空 PG 目标表")

    # 写入 PG（用 ORM 按表逐个写）
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # resource
        for r in sqlite_data["resource"]:
            db.add(Resource(**_strip(r)))
        db.flush()

        # project
        for p in sqlite_data["project"]:
            db.add(Project(**_strip(p)))
        db.flush()

        # phase
        for p in sqlite_data["phase"]:
            db.add(Phase(**_strip(p)))
        db.flush()

        # phase_assignee（关联表，直接 insert）
        for pa in sqlite_data["phase_assignee"]:
            db.execute(phase_assignee.insert().values(**_strip(pa)))

        # dependency
        for d in sqlite_data["dependency"]:
            db.add(Dependency(**_strip(d)))
        db.flush()

        # rework_log
        for rl in sqlite_data["rework_log"]:
            db.add(ReworkLog(**_strip(rl)))

        db.commit()
    finally:
        db.close()

    # 校验：PG 各表行数 vs SQLite
    print("\n校验行数：")
    all_ok = True
    with engine.connect() as conn:
        for t in _TABLES_ORDER:
            pg_count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            sqlite_count = len(sqlite_data[t])
            ok = "✓" if pg_count == sqlite_count else "✗"
            if pg_count != sqlite_count:
                all_ok = False
            print(f"  {ok} {t}: PG={pg_count} SQLite={sqlite_count}")

    if all_ok:
        print("\n✅ 迁移完成，行数全部一致")
    else:
        print("\n⚠️ 行数不一致，请检查")
        sys.exit(1)

    # 修复 PostgreSQL 自增序列（显式写入 ID 后必须同步）
    from sqlalchemy import text
    with engine.connect() as conn:
        tables = ["resource", "project", "phase", "dependency", "rework_log",
                   "template", "template_phase", "template_dependency", "user_account"]
        for t in tables:
            conn.execute(text(
                f"SELECT setval('{t}_id_seq', COALESCE((SELECT MAX(id) FROM {t}), 1))"
            ))
        conn.commit()
    print("✓ PostgreSQL 序列已同步到表最大 id")

    if all_ok:
        print("\n✅ 迁移完成，行数全部一致")
    else:
        print("\n⚠️ 行数不一致，请检查")
        sys.exit(1)


def _strip(row: dict) -> dict:
    """移除 None 值的键不必要处理，保留原样（ORM 会处理 None）。"""
    return {k: v for k, v in row.items()}


if __name__ == "__main__":
    main()
