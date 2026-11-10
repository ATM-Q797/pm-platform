"""每日快照 CLI（crontab 入口，PROJECT_ANALYSIS §3.4）。

    python -m app.jobs.snapshot

独立进程自建 SessionLocal：绕开 HTTP 鉴权，且 crontab 单进程天然无
gunicorn 多 worker 重复执行问题。幂等由 create_today_if_absent 保证。
退出码：0=成功（建行或跳过）；1=失败（crontab 只看退出码与日志——失败必须非零退出）。
"""
from __future__ import annotations


def main() -> int:
    from app.database import engine, session_scope  # 延迟导入：被 import 时不创建引擎
    from sqlalchemy import text

    from app.services.snapshot import create_today_if_absent, snapshot_projects_today

    def maintain_fn_exists() -> bool:
        # PG 专有 plpgsql 函数存在性检查（migrate_v6 才建；迁移未跑的库返回 False）
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'maintain_project_snapshots')"
            )).scalar_one()

    try:
        # 在会话内取出标量——session_scope 退出后实例已脱离会话，出块后再读属性会报
        with session_scope() as db:
            snapshot, created = create_today_if_absent(db)
            summary = (
                f"{snapshot.snapshot_date.isoformat()} "
                f"{'created' if created else 'skipped'} "
                f"projects_total={snapshot.metrics.get('projects_total')} "
                f"delayed_phases={snapshot.metrics.get('delayed_phases')} "
                f"conflict_pairs={snapshot.metrics.get('conflict_pairs')}"
            )
            # 8-3 项目级采集（批次档 §2 设计点 2：与全局快照同一 crontab 任务内写入）
            # upsert 幂等——crontab 重跑覆盖当日行不产生两行
            scanned, created_rows = snapshot_projects_today(db)
        print(f"[snapshot] {summary}")
        print(f"[snapshot] project_snapshots scanned={scanned} created={created_rows}")
        # 8-3 分层降采样（批次档 §2 设计点 3：crontab 周任务执行）——评审 #4 发现零调用方，
        # 日行会无限累积违反 §3.6 保留策略，故接进同一每日任务：函数幂等（周一锚点上卷，
        # 重跑无副作用），每天调一次 ≤ 每周调一次的维护效果，无需额外 crontab 条目。
        # 仅 PG 且函数已建（migrate_v6 后才有）——缺函数/非 PG 方言跳过不报错，
        # 避免迁移未跑的库被维护调用卡死（快照主流程已成功，不能被收尾步骤连坐）。
        if engine.dialect.name == "postgresql":
            if maintain_fn_exists():
                with engine.begin() as conn:
                    conn.execute(text("SELECT maintain_project_snapshots()"))
                print("[snapshot] maintain_project_snapshots() ok")
            else:
                print("[snapshot] maintain_project_snapshots() 不存在（先跑 deploy/migrate_v6.sql）——跳过")
        else:
            print("[snapshot] maintain_project_snapshots() skipped（非 PG 方言）")
        return 0
    except Exception as e:  # noqa: BLE001 —— CLI 边界：任何失败都要落日志并以非零退出
        print(f"[snapshot] FAILED: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
