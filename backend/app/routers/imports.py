"""Excel 导入 API 路由。

对应 PROJECT_SPEC §4.2 Excel 导入端点。
- POST /api/import/excel：上传 Excel 文件并全量导入
- GET /api/import/report：获取最近一次导入的校验报告
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models import User
from app.schemas.import_report import ImportPreview, ImportReport
from app.services import build_preview, get_last_report, import_excel, parse_workbook

router = APIRouter(prefix="/api/import", tags=["Excel导入"])


@router.post("/preview", response_model=ImportPreview)
async def preview_import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    default_category: str = "新需求",
    user: User = Depends(require_role("admin")),
):
    """上传 Excel 文件并生成导入前差异报告（只解析，不落库、无副作用）。

    返回：现有数据量（将被清空）/ 文件数据量 / 同名项目对比 / 错误与警告 / 项目概览。
    确认无误后再调用 POST /api/import/excel 真正导入。
    """
    # 校验文件扩展名
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "仅支持 .xlsx / .xls 文件")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "上传的文件为空")

    try:
        parsed = parse_workbook(file_bytes, default_category=default_category)
    except Exception as e:
        # 未预期的解析异常
        raise HTTPException(400, f"解析失败: {e}")

    return build_preview(db, parsed)


@router.post("/excel", response_model=ImportReport)
async def import_excel_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    default_category: str = "新需求",
    user: User = Depends(require_role("admin")),
):
    """上传 Excel 文件并导入（multipart/form-data）。

    全量重置：先删所有项目/阶段/资源（保留模板），再导入。
    返回导入校验报告（同步），并存为最近报告供 GET /api/import/report 查询。
    """
    # 校验文件扩展名
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "仅支持 .xlsx / .xls 文件")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "上传的文件为空")

    try:
        report = import_excel(db, file_bytes, default_category=default_category)
    except Exception as e:
        # 未预期的解析异常
        raise HTTPException(400, f"导入失败: {e}")

    return report


@router.get("/report", response_model=ImportReport)
def get_import_report():
    """获取最近一次导入的校验报告。无记录时返回 404。"""
    report = get_last_report()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "尚无导入报告，请先执行 POST /api/import/excel")
    return report
