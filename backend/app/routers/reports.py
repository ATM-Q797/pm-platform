"""周报 API（T7）。

- POST /api/reports/weekly：生成 Markdown 周报
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models import User
from app.services.weekly_report import build_weekly_report

router = APIRouter(prefix="/api/reports", tags=["周报"])


class WeeklyReportRequest(BaseModel):
    """周报生成请求：project_ids 不传 = 全部项目。"""
    project_ids: list[int] | None = None


@router.post("/weekly")
def generate_weekly_report(
    body: WeeklyReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
):
    """生成本周周报（Markdown + 纯文本）。

    内容：整体进度概览 / 风险预警（延期+即将到期）/ 本周完成 / 进行中 / 下周计划。
    """
    return build_weekly_report(db, body.project_ids)
