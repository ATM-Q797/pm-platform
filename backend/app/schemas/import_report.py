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
    # 合并模式统计（全量替换模式保持 0）
    projects_created: int = 0     # 新增项目数
    projects_updated: int = 0     # 更新项目数（同名合并）
    phases_created: int = 0       # 新增阶段数
    phases_updated: int = 0       # 更新阶段数
    pending_link_phases: list[PendingLinkPhase] = []  # 新增阶段待关联依赖清单


class PendingLinkPhase(BaseModel):
    """同名项目新增阶段：未自动建依赖，提示用户手动关联。"""
    project_name: str
    phase_name: str


# ---------- 导入前差异报告（预览） ----------

class ImportExistingCounts(BaseModel):
    """当前库中将被清空的数据量。"""
    projects: int = 0
    phases: int = 0
    resources: int = 0


class ImportIncomingCounts(BaseModel):
    """文件中将导入的数据量。"""
    projects: int = 0
    phases: int = 0


class ProjectMatchInfo(BaseModel):
    """文件项目名与现有项目名的对比（防传错文件）。"""
    matched: int = 0   # 文件中的项目与现有同名（将被覆盖重建）
    new: int = 0       # 文件新增的项目（现有没有）
    missing: int = 0   # 现有项目不在文件中（导入后将被删除）


class PreviewProject(BaseModel):
    """文件内单个项目的概览。"""
    name: str
    market: str
    category: str
    phases: int


class ImportPreview(BaseModel):
    """导入前差异报告：现有 vs 文件 + 问题清单 + 项目概览。"""
    existing: ImportExistingCounts = ImportExistingCounts()
    incoming: ImportIncomingCounts = ImportIncomingCounts()
    match: ProjectMatchInfo = ProjectMatchInfo()
    errors: list[ImportError] = []
    warnings: list[ImportWarning] = []
    projects_preview: list[PreviewProject] = []
    # 合并模式明细（增量合并：新增/更新/保留 + 待关联依赖提示）
    created_projects: list[PreviewProject] = []   # 文件新增项目
    updated_projects: list[PreviewProject] = []   # 同名将被合并更新的项目
    kept_count: int = 0                           # 现有项目不在文件中（合并模式保留不动）
    phases_created: int = 0                       # 文件将新增的阶段数
    phases_updated: int = 0                       # 文件将更新的阶段数
    pending_link_phases: list[PendingLinkPhase] = []  # 新增阶段待关联依赖提示
