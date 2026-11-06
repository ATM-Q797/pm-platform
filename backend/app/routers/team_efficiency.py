"""团队效率端点（PHASE8_PLAN §四 8-4，admin/manager 可见）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.team_efficiency import TeamEfficiency as TeamEfficiencySchema
from app.services.team_efficiency import compute_team_efficiency

router = APIRouter()


@router.get("/api/team-efficiency", response_model=TeamEfficiencySchema)
def list_team_efficiency(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=365, description="时间窗（天），只影响指标 3-5"),
):
    """团队效率六指标（admin/manager 专属——负荷与流程分析，不构成绩效评价）。"""
    if user.role not in ("admin", "manager"):
        from fastapi import HTTPException
        raise HTTPException(403, "仅 admin/manager 可查看团队效率")
    result = compute_team_efficiency(db, window_days=days)
    return result
