"""每日快照 CLI（crontab 入口，PROJECT_ANALYSIS §3.4）。

    python -m app.jobs.snapshot

独立进程自建 SessionLocal：绕开 HTTP 鉴权，且 crontab 单进程天然无
gunicorn 多 worker 重复执行问题。幂等由 create_today_if_absent 保证。
退出码：0=成功（建行或跳过）；1=失败（crontab 只看退出码与日志——失败必须非零退出）。
"""
from __future__ import annotations


def main() -> int:
    from app.database import session_scope  # 延迟导入：被 import 时不创建引擎
    from app.services.snapshot import create_today_if_absent

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
        print(f"[snapshot] {summary}")
        return 0
    except Exception as e:  # noqa: BLE001 —— CLI 边界：任何失败都要落日志并以非零退出
        print(f"[snapshot] FAILED: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
