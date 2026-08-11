"""Excel 导入器：解析项目进度 Excel，写入数据库。

支持两种格式（按表头自动识别）：
1. 新格式（14 列，docs/项目填报模板.xlsx，推荐）：
   项目编号 | 项目类目 | 项目名称 | 项目负责人 | 市场 | 阶段类型 |
   计划开始 | 计划结束 | 实际开始 | 实际结束 | 阶段负责人 | 阶段状态 | 阶段进度 | 备注
2. 旧格式（8 列，历史源文件）：
   项目编号 | 项目类目 | 项目名称 | 负责人 | 计划开始 | 计划结束 | 状态 | 交接人

通用规则：
- 数据从第 3 行开始（前 2 行表头）
- 项目编号：纯数字 = 项目行；数字-数字 = 阶段行；其他 = 备注行跳过
- 日期：openpyxl 已解析为 datetime；文本异常（如 '2026/-/--'）记 warning 设 NULL
- 多人字段：多空格/逗号分隔，拆分后逐人建/匹配 Resource

导入策略：全量重置（先删所有 Project/Phase/Dependency，清空 Resource，保留 Template）。
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project, Resource
from app.schemas.import_report import ImportError, ImportReport, ImportWarning

# ---------- 新格式（14 列，项目填报模板）列索引 ----------
_NEW_COL_CODE = 1
_NEW_COL_CATEGORY = 2
_NEW_COL_NAME = 3
_NEW_COL_OWNER = 4
_NEW_COL_MARKET = 5
_NEW_COL_PHASE_TYPE = 6
_NEW_COL_PLAN_START = 7
_NEW_COL_PLAN_END = 8
_NEW_COL_ACTUAL_START = 9
_NEW_COL_ACTUAL_END = 10
_NEW_COL_ASSIGNEES = 11
_NEW_COL_STATUS = 12
_NEW_COL_PROGRESS = 13
_NEW_COL_REMARK = 14

# ---------- 旧格式（8 列，历史源文件）列索引 ----------
_OLD_COL_CODE = 1
_OLD_COL_CATEGORY = 2
_OLD_COL_NAME = 3
_OLD_COL_OWNER = 4
_OLD_COL_PLAN_START = 5
_OLD_COL_PLAN_END = 6
_OLD_COL_STATUS = 7
_OLD_COL_HANDOVER = 8  # 旧格式读取但不再写入数据库（字段已废弃）

# 数据起始行（前 2 行表头）
_DATA_START_ROW = 3

# 项目编号正则：纯数字=项目，数字-数字=阶段
_PROJECT_CODE_RE = re.compile(r"^\d+$")
_PHASE_CODE_RE = re.compile(r"^\d+-\d+$")

# 多人字段拆分正则：任意空白/中英文逗号
_PERSON_SPLIT_RE = re.compile(r"[\s,，]+")

# 阶段类型前缀（新格式 "P4 工业设计" → code=P4, name=工业设计）
_PHASE_TYPE_PREFIX_RE = re.compile(r"^(P[1-8])\s*(.*)$")

# 阶段名 → phase_type 映射表（旧格式/新格式阶段类型列缺省时的兜底）
# 基础部分来自 PROJECT_SPEC §5.3；扩充部分覆盖实际 Excel 里的阶段名变体。
# key 为阶段名（trim 后），value 为 phase_type。
PHASE_NAME_TO_TYPE: dict[str, str] = {
    # --- 基础映射（§5.3 原表）---
    "工业设计": "P4",
    "结构设计": "P5",
    "整机设计": "P5",
    "样机打样": "P6",
    "联调测试": "P7",
    "测试": "P7",
    "POC及投标": "P8",
    "需求分析": "P1",
    "需求评估": "P1",
    "配置评估": "P2",
    "模块选型": "P3",
    "直接投料": "P8",
    "图纸归档": "P5",
    "归档": "P5",
    "BOM制作与激活": "P8",
    "首批生产保障": "P8",
    "投料": "P8",
    "发货": "P8",
    # --- 扩充映射（实际 Excel 里的阶段名变体）---
    "测试与发货": "P8",          # = 交付
    "样机打样（1台）": "P6",     # = 样机打样
    "归档（归档后再投料）": "P8", # 量产阶段的归档后投料 = 交付（区别于设计阶段的"归档"P5）
    "直接投料，BOM制作与激活": "P8",  # = 交付
    "直接投料，激活时间": "P8",   # = 交付
    "交付": "P8",               # = 交付（直白词，§5.3 原表遗漏）
}

# 新格式表头关键字（识别用）
_NEW_FORMAT_KEYS = ("项目编号", "阶段类型", "市场")
_OLD_FORMAT_KEYS = ("项目编号", "交接人")

# 进程内存：最近一次导入报告（供 GET /api/import/report 查询）
_last_report: ImportReport | None = None


def get_last_report() -> ImportReport | None:
    return _last_report


def _set_last_report(report: ImportReport | None) -> None:
    global _last_report
    _last_report = report


# ---------- 清洗工具函数 ----------

def parse_cell_date(value: Any, row: int, sheet: str, field: str, report: ImportReport) -> date | None:
    """解析日期单元格。

    - datetime/date 对象 → 直接取 date
    - 文本 'YYYY-MM-DD'（模板/手工填写的常见格式）→ fromisoformat 解析
    - 文本异常（如 '2026/-/--'）→ NULL + warning
    - None → None
    - 数字（Excel 序列号）→ 按 1899-12-30 基准转换
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel 日期序列号基准
        try:
            return (date(1899, 12, 30) + __import__("datetime").timedelta(days=int(value)))
        except Exception:
            pass
    # 文本：先试 ISO 格式（YYYY-MM-DD），失败则记 warning
    text = str(value).strip()
    if text:
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    report.warnings.append(ImportWarning(
        row=row, sheet=sheet, field=field,
        message=f"无法解析日期 '{text}'，已设为空",
    ))
    return None


def split_persons(value: Any) -> list[str]:
    """拆分多人字段，返回去重后的人员姓名列表。"""
    if value is None or value == "":
        return []
    # 清除换行，取有效内容
    text = str(value).replace("\n", " ").strip()
    parts = [p.strip() for p in _PERSON_SPLIT_RE.split(text) if p.strip()]
    # 去重保序
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        if p not in seen and p != "/":  # "/" 在原表表示无
            seen.add(p)
            result.append(p)
    return result


def classify_row(code: Any, name: Any) -> str:
    """行分类：'project' | 'phase' | 'skip'（空行/备注行）。"""
    if code is None and name is None:
        return "skip"
    code_s = str(code).strip() if code is not None else ""
    if _PROJECT_CODE_RE.match(code_s):
        return "project"
    if _PHASE_CODE_RE.match(code_s):
        return "phase"
    return "skip"  # 备注/图例/长文本行


def map_phase_type(name: str, row: int, sheet: str, report: ImportReport) -> str | None:
    """阶段名 → phase_type。无法映射的记 error 并返回 None。"""
    phase_type = PHASE_NAME_TO_TYPE.get(name.strip())
    if phase_type is None:
        report.errors.append(ImportError(
            row=row, sheet=sheet, field="name",
            message=f"阶段名'{name}'无法映射到 phase_type（详见 PROJECT_SPEC §5.3 映射表）",
        ))
    return phase_type


def parse_phase_type_cell(value: Any) -> tuple[str, str] | None:
    """解析新格式"阶段类型"列（如 'P4 工业设计'）→ (phase_type, name)。

    - 带前缀（P1-P8 + 名称）→ 拆分
    - 仅前缀（'P4'）→ name 用前缀本身
    - 无前缀或空 → None（走映射表兜底）
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = _PHASE_TYPE_PREFIX_RE.match(text)
    if m and m.group(1):
        name = m.group(2).strip() or m.group(1)
        return m.group(1), name
    return None


def _market_from_sheet(sheet_name: str) -> str:
    """旧格式：根据 sheet 名推断市场。"""
    if "海外" in sheet_name:
        return "海外"
    return "国内"


def detect_format(ws) -> str:
    """按表头识别格式：'new'（14列模板）| 'old'（8列历史）| 'unknown'。"""
    header = ""
    for r in (1, 2):
        for c in range(1, 16):
            v = ws.cell(r, c).value
            if v is not None:
                header += str(v)
    if all(k in header for k in _NEW_FORMAT_KEYS):
        return "new"
    if all(k in header for k in _OLD_FORMAT_KEYS):
        return "old"
    return "unknown"


# ---------- 资源缓存（一次导入内复用） ----------

def _get_or_create_resource(db: Session, cache: dict[str, Resource], name: str) -> Resource:
    """按姓名查/建 Resource，缓存避免重复查询。"""
    if name in cache:
        return cache[name]
    r = db.scalars(select(Resource).where(Resource.name == name)).first()
    if r is None:
        r = Resource(name=name)
        db.add(r)
        db.flush()
    cache[name] = r
    return r


# ---------- 主导入流程 ----------

def import_excel(db: Session, file_bytes: bytes, default_category: str = "新需求") -> ImportReport:
    """解析 Excel 文件并全量导入。

    全量重置：先删所有 Project（级联 Phase/Dependency）、清空 Resource（保留 Template）。
    返回 ImportReport，并存为最近报告供 GET /api/import/report 查询。
    """
    report = ImportReport()

    # 解析工作簿
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        report.errors.append(ImportError(
            row=0, sheet="(文件)", field="file",
            message=f"无法读取 Excel 文件: {e}",
        ))
        _set_last_report(report)
        return report

    # 选 sheet：识别出格式（new/old）的数据 sheet；'unknown'（如"填报说明"）跳过
    target_sheets = [(name, detect_format(wb[name])) for name in wb.sheetnames]
    target_sheets = [(n, f) for n, f in target_sheets if f != "unknown"]

    if not target_sheets:
        report.errors.append(ImportError(
            row=0, sheet="(文件)", field="file",
            message=(
                "Excel 中未找到可识别的数据工作表。请使用「项目填报模板.xlsx」"
                "（表头含：项目编号/项目类目/项目名称/项目负责人/市场/阶段类型）"
            ),
        ))
        _set_last_report(report)
        return report

    # 全量重置：删 Project（级联）+ Resource（保留 Template）
    db.query(Project).delete()
    db.query(Resource).delete()
    db.flush()

    resource_cache: dict[str, Resource] = {}
    resources_created = 0
    # 全局项目编号计数器：跨 sheet 连续编号（1,2,3...），避免两表编号冲突
    project_seq = 0

    for sheet_name, fmt in target_sheets:
        ws = wb[sheet_name]
        # 当前项目（阶段挂载用）：遇到项目行时更新
        current_project: Project | None = None
        current_project_phases: list[Phase] = []  # 用于按 sequence 建依赖

        for r in range(_DATA_START_ROW, ws.max_row + 1):
            if fmt == "new":
                row_vals = _read_new_format_row(ws, r)
            else:
                row_vals = _read_old_format_row(ws, r)
            code, category, name, owner, plan_start_raw, plan_end_raw, status = row_vals[:7]
            actual_start_raw, actual_end_raw, phase_type_cell, assignees, progress, remark, market = row_vals[7:]

            report.total_rows += 1
            row_kind = classify_row(code, name)

            if row_kind == "skip":
                continue

            name_str = str(name).strip() if name is not None else ""
            status_str = str(status).strip() if status is not None else "未开始"

            if row_kind == "project":
                # 项目行
                owner_str = str(owner).strip() if owner is not None else ""
                plan_start = parse_cell_date(plan_start_raw, r, sheet_name, "plan_start", report)
                plan_end = parse_cell_date(plan_end_raw, r, sheet_name, "plan_end", report)
                market_str = str(market).strip() if market else (_market_from_sheet(sheet_name) if fmt == "old" else "")

                # 项目编号：按导入顺序连续编号（1,2,3...），跨 sheet 统一序列，不分市场。
                project_seq += 1
                unique_code = str(project_seq)

                # 新格式优先用列内类目；旧格式沿用 default_category（历史行为）
                cat = str(category).strip() if fmt == "new" and category else default_category

                project = Project(
                    code=unique_code,
                    category=cat or default_category,
                    name=name_str,
                    owner=owner_str,
                    market=market_str or "国内",
                    status=status_str or "未开始",
                    plan_start=plan_start,
                    plan_end=plan_end,
                    remark=str(remark).strip() if remark else None,
                )
                db.add(project)
                db.flush()
                current_project = project
                current_project_phases = []
                report.projects_imported += 1
                # 项目负责人也作为资源
                if owner_str:
                    before = len(resource_cache)
                    _get_or_create_resource(db, resource_cache, owner_str)
                    if len(resource_cache) > before:
                        resources_created += 1

            elif row_kind == "phase":
                # 阶段行
                if current_project is None:
                    report.errors.append(ImportError(
                        row=r, sheet=sheet_name, field="project_id",
                        message=f"阶段'{name_str}'缺少父项目（项目编号 {code}），跳过",
                    ))
                    continue

                # 阶段类型与名称：新格式优先解析"阶段类型"列。
                # - 带前缀（'P4 工业设计'）→ 拆 code + name
                # - 纯中文（'工业设计'）→ 整格文本作为阶段名，走映射表兜底
                # - 名称列有值时优先用名称列
                pt = parse_phase_type_cell(phase_type_cell)
                if pt:
                    phase_type, type_name = pt
                    phase_name = name_str or type_name
                else:
                    cell_text = str(phase_type_cell).strip() if phase_type_cell is not None else ""
                    phase_type = None
                    phase_name = name_str or cell_text
                if not phase_type:
                    phase_type = map_phase_type(phase_name, r, sheet_name, report)
                    if phase_type is None:
                        phase_type = ""

                plan_start = parse_cell_date(plan_start_raw, r, sheet_name, "plan_start", report)
                plan_end = parse_cell_date(plan_end_raw, r, sheet_name, "plan_end", report)
                actual_start = parse_cell_date(actual_start_raw, r, sheet_name, "actual_start", report)
                actual_end = parse_cell_date(actual_end_raw, r, sheet_name, "actual_end", report)

                # sequence 从项目编号的子序号提取（如 1-3 → 3）
                seq_match = re.search(r"-(\d+)$", str(code).strip())
                sequence = int(seq_match.group(1)) if seq_match else len(current_project_phases) + 1

                # 进度：显式列优先（新格式），否则按状态推断
                if progress is not None and str(progress).strip() not in ("", "/"):
                    try:
                        p = int(float(str(progress).strip()))
                        progress_val = max(0, min(100, p))
                    except ValueError:
                        progress_val = 100 if status_str == "已完成" else (50 if status_str == "进行中" else 0)
                else:
                    progress_val = 100 if status_str == "已完成" else (50 if status_str == "进行中" else 0)

                phase = Phase(
                    project_id=current_project.id,
                    phase_type=phase_type,
                    name=phase_name,
                    sequence=sequence,
                    plan_start=plan_start,
                    plan_end=plan_end,
                    actual_start=actual_start,
                    actual_end=actual_end,
                    status=status_str or "未开始",
                    progress=progress_val,
                    rework_count=0,
                    remark=str(remark).strip() if remark else None,
                )
                db.add(phase)
                db.flush()
                current_project_phases.append(phase)
                report.phases_imported += 1

                # 拆分负责人，建/匹配 Resource 并关联
                persons = split_persons(assignees)
                if persons:
                    assignee_resources = []
                    for pname in persons:
                        before = len(resource_cache)
                        res = _get_or_create_resource(db, resource_cache, pname)
                        if len(resource_cache) > before:
                            resources_created += 1
                        assignee_resources.append(res)
                    phase.assignees = assignee_resources

    # 收尾：对所有项目的阶段按 sequence 建 FS 串联依赖
    _build_all_project_dependencies(db)

    report.resources_created = resources_created
    db.commit()

    _set_last_report(report)
    return report


def _read_new_format_row(ws, r: int) -> list[Any]:
    """读取 14 列新格式一行，返回固定顺序的值列表。

    返回: [code, category, name, owner, plan_start, plan_end, status,
           actual_start, actual_end, phase_type, assignees, progress, remark, market]
    """
    return [
        ws.cell(r, _NEW_COL_CODE).value,
        ws.cell(r, _NEW_COL_CATEGORY).value,
        ws.cell(r, _NEW_COL_NAME).value,
        ws.cell(r, _NEW_COL_OWNER).value,
        ws.cell(r, _NEW_COL_PLAN_START).value,
        ws.cell(r, _NEW_COL_PLAN_END).value,
        ws.cell(r, _NEW_COL_STATUS).value,
        ws.cell(r, _NEW_COL_ACTUAL_START).value,
        ws.cell(r, _NEW_COL_ACTUAL_END).value,
        ws.cell(r, _NEW_COL_PHASE_TYPE).value,
        ws.cell(r, _NEW_COL_ASSIGNEES).value,
        ws.cell(r, _NEW_COL_PROGRESS).value,
        ws.cell(r, _NEW_COL_REMARK).value,
        ws.cell(r, _NEW_COL_MARKET).value,
    ]


def _read_old_format_row(ws, r: int) -> list[Any]:
    """读取 8 列旧格式一行，返回与新格式相同的顺序。

    返回: [code, category, name, owner, plan_start, plan_end, status,
           actual_start, actual_end, phase_type, assignees, progress, remark, market]
    - 旧格式无 实际日期/阶段类型/进度/备注 列 → None
    - 阶段行负责人 = 第 4 列（负责人列）
    - 交接人（第 8 列）读取后丢弃（字段已废弃）
    """
    return [
        ws.cell(r, _OLD_COL_CODE).value,
        ws.cell(r, _OLD_COL_CATEGORY).value,
        ws.cell(r, _OLD_COL_NAME).value,
        ws.cell(r, _OLD_COL_OWNER).value,
        ws.cell(r, _OLD_COL_PLAN_START).value,
        ws.cell(r, _OLD_COL_PLAN_END).value,
        ws.cell(r, _OLD_COL_STATUS).value,
        None,  # actual_start
        None,  # actual_end
        None,  # phase_type 列（旧格式无，走名称映射）
        ws.cell(r, _OLD_COL_OWNER).value,  # assignees = 负责人列
        None,  # progress
        None,  # remark
        None,  # market（旧格式按 sheet 名推断）
    ]


def _build_sequence_dependencies(db: Session, phases: list[Phase]) -> None:
    """按 sequence 升序，相邻阶段建 FS 依赖（phase[i] → phase[i+1]）。"""
    if len(phases) < 2:
        return
    ordered = sorted(phases, key=lambda p: p.sequence)
    for i in range(len(ordered) - 1):
        frm, to = ordered[i], ordered[i + 1]
        if frm.id == to.id:
            continue
        # 避免重复
        exists = db.scalars(
            select(Dependency).where(
                Dependency.from_phase_id == frm.id,
                Dependency.to_phase_id == to.id,
            )
        ).first()
        if exists:
            continue
        db.add(Dependency(from_phase_id=frm.id, to_phase_id=to.id, type="FS", lag_days=0))


def _build_all_project_dependencies(db: Session) -> None:
    """对所有项目的阶段按 sequence 建 FS 串联依赖。

    导入流程的每个项目阶段建好后调用。
    """
    projects = list(db.scalars(select(Project)))
    for project in projects:
        phases = list(db.scalars(
            select(Phase).where(Phase.project_id == project.id).order_by(Phase.sequence)
        ))
        _build_sequence_dependencies(db, phases)
