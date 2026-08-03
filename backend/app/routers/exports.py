"""Excel 导出 API。

把当前所有项目+阶段导出为 Excel，格式与导入源文件对齐：
- 两个 sheet：项目情况统计-国内 / 项目情况统计-海外
- 列：项目编号 | 项目类目 | 项目名称 | 负责人 | 计划开始 | 计划结束 | 状态 | 交接人
- 项目行编号为纯数字，阶段行编号为"项目编号-序号"
"""
from __future__ import annotations

import io
from datetime import date
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, Project

router = APIRouter(prefix="/api/export", tags=["Excel导出"])

# 列标题（与导入源文件一致）
_HEADERS = ["项目编号", "项目类目", "项目名称", "负责人", "计划开始", "计划结束", "状态", "交接人"]


def _write_sheet(ws, projects: list[Project]) -> None:
    """把一组项目写入工作表。项目行用纯数字编号，阶段行用'编号-序号'。"""
    # 表头 2 行（第 1 行列名，第 2 行留空，与源文件一致）
    ws.append(_HEADERS)
    ws.append([""] * len(_HEADERS))

    for proj_idx, project in enumerate(projects, start=1):
        # 项目行
        ws.append([
            proj_idx,
            project.category,
            project.name,
            project.owner,
            project.plan_start,
            project.plan_end,
            project.status,
            project.remark or "",
        ])
        # 阶段行（按 sequence 排序）
        phases = sorted(project.phases, key=lambda p: p.sequence)
        for seq, ph in enumerate(phases, start=1):
            # 负责人：多人用空格连接
            owner = " ".join(a.name for a in ph.assignees) if ph.assignees else ""
            ws.append([
                f"{proj_idx}-{seq}",
                ph.name,  # 类目列放阶段名（与导入时阶段行的类目列一致）
                ph.name,
                owner,
                ph.plan_start,
                ph.plan_end,
                ph.status,
                ph.handover_to or "",
            ])


@router.get("/excel")
def export_excel(db: Session = Depends(get_db)):
    """导出所有项目为 Excel 文件（国内/海外两个 sheet）。"""
    wb = openpyxl.Workbook()

    all_projects = list(db.scalars(select(Project).order_by(Project.id)))

    # 按市场分组
    domestic = [p for p in all_projects if p.market == "国内"]
    overseas = [p for p in all_projects if p.market == "海外"]

    # 国内 sheet（重命名默认 sheet）
    ws_domestic = wb.active
    ws_domestic.title = "项目情况统计-国内"
    _write_sheet(ws_domestic, domestic)

    # 海外 sheet
    ws_overseas = wb.create_sheet("项目情况统计-海外")
    _write_sheet(ws_overseas, overseas)

    # 输出到内存
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    today = date.today().isoformat()
    filename = f"项目进度导出-{today}.xlsx"
    # HTTP header 不支持非 ASCII，用 RFC 5987 filename* 编码中文文件名
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"export-{today}.xlsx\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
