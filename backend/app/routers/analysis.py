"""项目分析 API（PROJECT_ANALYSIS §3.2）。

- POST /api/analysis/snapshots/run  admin/观察者 手动触发/部署日建基线
  （幂等：首次 201 建行、同日再调 200 skipped；日常积累走 jobs/snapshot.py CLI + crontab）
- GET  /api/analysis/trend?days=30|90|180  登录即可（与看板一致）——日级点位 + 周级聚合
- GET  /api/analysis/process-audit?days=30|90|365  登录即可（P3 三指标，审计透明与 P1 事件端点同立场）
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models import StatusSnapshot, User
from app.schemas import AnalysisTrend, SnapshotRunResult
from app.schemas.analysis import ProcessAuditResult
from app.services.process_audit import compute_process_audit
from app.services.snapshot import build_trend, create_today_if_absent

router = APIRouter(prefix="/api/analysis", tags=["项目分析"])

_TREND_DAYS = (30, 90, 180)
_PROCESS_AUDIT_DAYS = (30, 90, 365)  # §4.6 批复口径三档（与 8-3 趋势图同款交互）


@router.post("/snapshots/run", response_model=SnapshotRunResult)
def run_snapshot(
    response: Response,
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "viewer")),
) -> SnapshotRunResult:
    """手动触发当日快照（幂等：建行 201 / 当日已有 200）。

    force=True（分析弹窗"数据刷新"按钮）：当日已有也重新采集覆盖，立即反映最新项目数据。
    角色门：admin/观察者（用户 2026-11-12 裁定「这个权限还是要给的」——数据刷新是派生数据重采，
    不属业务数据编辑；工程师权限维持原状 403）。reporter 由封锁矩阵挡（/api/analysis 非放行面）。
    """
    snapshot, created = create_today_if_absent(db, force=force)
    response.status_code = 201 if created else 200
    return SnapshotRunResult(
        snapshot_date=snapshot.snapshot_date.isoformat(),
        created=created,
        metrics=snapshot.metrics,
    )


@router.get("/trend", response_model=AnalysisTrend)
def get_trend(
    days: int = 30,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AnalysisTrend:
    """趋势数据（日级点位 + 周级聚合，差分查询时算）。"""
    if days not in _TREND_DAYS:
        raise HTTPException(400, f"days 非法：{days}（仅支持 {'|'.join(map(str, _TREND_DAYS))}）")
    rows = db.scalars(select(StatusSnapshot).order_by(StatusSnapshot.snapshot_date)).all()
    data = build_trend(rows, days, today=date.today())
    return AnalysisTrend(**data)


@router.get("/process-audit", response_model=ProcessAuditResult)
def get_process_audit(
    days: int = 90,
    market: str | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProcessAuditResult:
    """过程审计三指标（P3，PHASE8_PLAN §九）：计划稳定性/估算偏差/审批时效。

    登录即可查（审计透明，与 P1 事件端点同立场）；reporter 由封锁矩阵挡（/api/analysis 非放行面）。
    days 30/90/365 三档（§4.6 批复口径）；market 锚 Project.market（可选）；project_id 单项目明细（可选）。
    防火墙：返回体无按人维度（不做绩效评分/排名）。
    """
    if days not in _PROCESS_AUDIT_DAYS:
        raise HTTPException(400, f"days 非法：{days}（仅支持 {'|'.join(map(str, _PROCESS_AUDIT_DAYS))}）")
    data = compute_process_audit(db, days=days, market=market, project_id=project_id)
    return ProcessAuditResult(**data)
