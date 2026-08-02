"""Excel 导入器：解析项目进度 Excel，写入数据库。

对应 PROJECT_SPEC §5。

真实 Excel 结构（经数据探查确认）：
- 数据从第 3 行开始（前 2 行表头）
- 前 8 列：项目编号 | 项目类目 | 项目名称 | 负责人 | 计划开始 | 计划结束 | 状态 | 交接人
- 项目编号：纯数字 = 项目行；数字-数字 = 阶段行；其他 = 备注行跳过
- 日期：openpyxl 已解析为 datetime；文本异常（如 '2026/-/--'）记 warning 设 NULL
- 多人字段：多空格/逗号分隔，拆分后逐人建/匹配 Resource

导入策略：全量重置（先删所有 Project/Phase/Dependency，清空 Resource，保留 Template）。
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project, Resource
from app.schemas.import_report import ImportError, ImportReport, ImportWarning

# Excel 列索引（1-based）：项目编号=1 ... 交接人=8
_COL_CODE = 1
_COL_CATEGORY = 2
_COL_NAME = 3
_COL_OWNER = 4
_COL_PLAN_START = 5
_COL_PLAN_END = 6
_COL_STATUS = 7
_COL_HANDOVER = 8

# 数据起始行（前 2 行表头）
_DATA_START_ROW = 3

# 项目编号正则：纯数字=项目，数字-数字=阶段
_PROJECT_CODE_RE = re.compile(r"^\d+$")
_PHASE_CODE_RE = re.compile(r"^\d+-\d+$")

# 多人字段拆分正则：任意空白/中英文逗号
_PERSON_SPLIT_RE = re.compile(r"[\s,，]+")

# 阶段名 → phase_type 映射表
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
}

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
    # 文本：尝试解析，失败则记 warning
    text = str(value).strip()
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


def _market_from_sheet(sheet_name: str) -> str:
    """根据 sheet 名推断市场。"""
    if "海外" in sheet_name:
        return "海外"
    return "国内"


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

    # 选 sheet：优先含"国内""海外"的，否则用全部
    sheet_names = wb.sheetnames
    target_sheets = [s for s in sheet_names if "国内" in s or "海外" in s]
    if not target_sheets:
        target_sheets = sheet_names

    if not target_sheets:
        report.errors.append(ImportError(
            row=0, sheet="(文件)", field="file",
            message="Excel 文件中未找到任何工作表",
        ))
        _set_last_report(report)
        return report

    # 全量重置：删 Project（级联）+ Resource（保留 Template）
    db.query(Project).delete()
    db.query(Resource).delete()
    db.flush()

    resource_cache: dict[str, Resource] = {}
    resources_created = 0
    # 全局项目编号计数器：国内/海外的项目连续编号（1,2,3...），避免两表编号冲突
    project_seq = 0

    for sheet_name in target_sheets:
        ws = wb[sheet_name]
        market = _market_from_sheet(sheet_name)
        # 当前项目（阶段挂载用）：遇到项目行时更新
        current_project: Project | None = None
        current_project_phases: list[Phase] = []  # 用于按 sequence 建依赖

        for r in range(_DATA_START_ROW, ws.max_row + 1):
            code = ws.cell(r, _COL_CODE).value
            category = ws.cell(r, _COL_CATEGORY).value
            name = ws.cell(r, _COL_NAME).value
            owner = ws.cell(r, _COL_OWNER).value
            plan_start_raw = ws.cell(r, _COL_PLAN_START).value
            plan_end_raw = ws.cell(r, _COL_PLAN_END).value
            status = ws.cell(r, _COL_STATUS).value
            handover = ws.cell(r, _COL_HANDOVER).value

            report.total_rows += 1
            row_kind = classify_row(code, name)

            if row_kind == "skip":
                continue

            name_str = str(name).strip() if name is not None else ""
            status_str = str(status).strip() if status is not None else "未开始"
            handover_str = str(handover).strip() if handover is not None else ""
            if handover_str == "/":
                handover_str = ""

            if row_kind == "project":
                # 项目行
                owner_str = str(owner).strip() if owner is not None else ""
                plan_start = parse_cell_date(plan_start_raw, r, sheet_name, "plan_start", report)
                plan_end = parse_cell_date(plan_end_raw, r, sheet_name, "plan_end", report)

                # 项目编号：按导入顺序连续编号（1,2,3...），国内/海外统一序列，不分市场。
                project_seq += 1
                unique_code = str(project_seq)

                project = Project(
                    code=unique_code,
                    category=default_category,
                    name=name_str,
                    owner=owner_str,
                    market=market,
                    status=status_str or "未开始",
                    plan_start=plan_start,
                    plan_end=plan_end,
                    remark=None,
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

                phase_type = map_phase_type(name_str, r, sheet_name, report)
                plan_start = parse_cell_date(plan_start_raw, r, sheet_name, "plan_start", report)
                plan_end = parse_cell_date(plan_end_raw, r, sheet_name, "plan_end", report)

                # sequence 从项目编号的子序号提取（如 1-3 → 3）
                seq_match = re.search(r"-(\d+)$", str(code).strip())
                sequence = int(seq_match.group(1)) if seq_match else len(current_project_phases) + 1

                phase = Phase(
                    project_id=current_project.id,
                    phase_type=phase_type if phase_type else "",
                    name=name_str,
                    sequence=sequence,
                    plan_start=plan_start,
                    plan_end=plan_end,
                    status=status_str or "未开始",
                    progress=100 if status_str == "已完成" else (50 if status_str == "进行中" else 0),
                    rework_count=0,
                    handover_to=handover_str or None,
                )
                db.add(phase)
                db.flush()
                current_project_phases.append(phase)
                report.phases_imported += 1

                # 拆分负责人，建/匹配 Resource 并关联
                persons = split_persons(owner)
                if persons:
                    assignees = []
                    for pname in persons:
                        before = len(resource_cache)
                        res = _get_or_create_resource(db, resource_cache, pname)
                        if len(resource_cache) > before:
                            resources_created += 1
                        assignees.append(res)
                    phase.assignees = assignees

    # 收尾：对所有项目的阶段按 sequence 建 FS 串联依赖
    _build_all_project_dependencies(db)

    report.resources_created = resources_created
    db.commit()

    _set_last_report(report)
    return report


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
