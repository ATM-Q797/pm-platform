"""Excel 导出 API。

把当前所有项目+阶段导出为 Excel，格式与「项目填报模板.xlsx」对齐（14 列）：
- 单 sheet：项目填报
- 列：项目编号 | 项目类目 | 项目名称 | 项目负责人 | 市场 | 阶段类型 |
      计划开始 | 计划结束 | 实际开始 | 实际结束 | 阶段负责人 | 阶段状态 | 阶段进度 | 备注
- 项目行编号为纯数字，阶段行编号为"项目编号-序号"
"""
from __future__ import annotations

import io
from datetime import date
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user
from app.models import Phase, Project, User
from app.services.excel_format import HEADERS, style_sheet

router = APIRouter(prefix="/api/export", tags=["Excel导出"])


def _phase_type_label(ph: Phase) -> str:
    """阶段类型列文本：直接使用阶段名称（不含 P1-P8 前缀）。"""
    return ph.name


def _write_sheet(ws, projects: list[Project]) -> None:
    """把全部项目写入工作表（布局与填报模板一致：R1 标题 / R2 表头 / R3 起数据）。"""
    # 第 1 行：标题
    ws.append(["智能终端研发项目管理平台 — 项目填报模板"])
    # 第 2 行：表头
    ws.append(HEADERS)
    # 第 3 行起：数据

    for proj_idx, project in enumerate(projects, start=1):
        # 项目行
        ws.append([
            proj_idx,
            project.category,
            project.name,
            project.owner,
            project.market,
            "",  # 阶段类型
            project.plan_start,
            project.plan_end,
            "",  # 实际开始
            "",  # 实际结束
            "",  # 阶段负责人
            "",  # 阶段状态
            "",  # 阶段进度
            project.remark or "",
        ])
        # 阶段行（按 sequence 排序）
        phases = sorted(project.phases, key=lambda p: p.sequence)
        for seq, ph in enumerate(phases, start=1):
            # 负责人：多人用空格连接
            owner = " ".join(a.name for a in ph.assignees) if ph.assignees else ""
            ws.append([
                f"{proj_idx}-{seq}",
                "",  # 类目
                "",  # 名称（阶段名在"阶段类型"列）
                "",  # 项目负责人
                "",  # 市场
                _phase_type_label(ph),
                ph.plan_start,
                ph.plan_end,
                ph.actual_start,
                ph.actual_end,
                owner,
                ph.status,
                ph.progress,
                ph.remark or "",
            ])


@router.get("/excel")
def export_excel(special: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """导出项目为 Excel 文件（单 sheet，与填报模板格式一致）。

    - special=false（默认）：常规项目域（专项排除，SPECIAL_PROJECT §4.3）
    - special=true：专项项目域（仅 admin/manager，用户 2026-08-28）
    """
    if special and user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="仅管理员/经理可导出专项项目")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "项目填报"
    all_projects = list(db.scalars(
        select(Project).where(
            Project.is_special.is_(True) if special else Project.is_special.is_(False)
        ).order_by(Project.id)
    ))
    _write_sheet(ws, all_projects)
    # 应用模板样式与数据验证（列宽/边框/冻结/下拉/日期验证）
    style_sheet(ws)

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
