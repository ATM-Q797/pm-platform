"""项目分析 API（PROJECT_ANALYSIS §3.2）。

- POST /api/analysis/snapshots/run  admin 手动触发/部署日建基线
  （幂等：首次 201 建行、同日再调 200 skipped；日常积累走 jobs/snapshot.py CLI + crontab）
- GET  /api/analysis/trend?days=30|90|180  登录即可（与看板一致）——日级点位 + 周级聚合
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
from app.services.snapshot import build_trend, create_today_if_absent

router = APIRouter(prefix="/api/analysis", tags=["项目分析"])

_TREND_DAYS = (30, 90, 180)


@router.post("/snapshots/run", response_model=SnapshotRunResult)
def run_snapshot(
    response: Response,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> SnapshotRunResult:
    """手动触发当日快照（幂等：建行 201 / 当日已有 200）。"""
    snapshot, created = create_today_if_absent(db)
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
