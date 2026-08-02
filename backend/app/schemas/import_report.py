"""Excel 导入校验报告的 Pydantic 模型。

对应 PROJECT_SPEC §5.5。
"""
from __future__ import annotations

from pydantic import BaseModel


class ImportError(BaseModel):
    """一条错误：阶段名无法映射、必填字段缺失等（不中断导入，记录备查）。"""
    row: int
    sheet: str
    field: str
    message: str


class ImportWarning(BaseModel):
    """一条警告：日期无法解析（已设空）、单元格换行（已清除）等。"""
    row: int
    sheet: str
    field: str
    message: str


class ImportReport(BaseModel):
    """导入报告汇总。"""
    total_rows: int = 0
    projects_imported: int = 0
    phases_imported: int = 0
    resources_created: int = 0
    errors: list[ImportError] = []
    warnings: list[ImportWarning] = []
