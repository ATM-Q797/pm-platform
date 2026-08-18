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
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import openpyxl
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project, Resource, User
from app.schemas.import_report import (
    ImportError,
    ImportExistingCounts,
    ImportIncomingCounts,
    ImportPreview,
    ImportReport,
    ImportWarning,
    PendingLinkPhase,
    PreviewProject,
    ProjectMatchInfo,
)

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


# ---------- 内存数据结构（解析阶段产出，零 DB 副作用） ----------

@dataclass
class ParsedPhase:
    """解析出的阶段（未落库）。"""
    name: str
    phase_type: str
    sequence: int
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    status: str = "未开始"
    progress: int = 0
    remark: str | None = None
    assignees: list[str] = field(default_factory=list)
    # 显式标记：单元格是否有值（合并模式下"未填"不覆盖系统值）
    status_explicit: bool = False
    progress_explicit: bool = False


@dataclass
class ParsedProject:
    """解析出的项目（未落库），phases 内按 sequence 有序。"""
    code: str
    category: str
    name: str
    owner: str
    market: str
    status: str
    plan_start: date | None = None
    plan_end: date | None = None
    remark: str | None = None
    phases: list[ParsedPhase] = field(default_factory=list)
    # 显式标记：项目状态单元格是否有值（合并模式下"未填"不覆盖系统状态）
    status_explicit: bool = False


@dataclass
class ParsedWorkbook:
    """解析结果：项目列表 + 解析报告（errors/warnings/统计）。"""
    projects: list[ParsedProject]
    report: ImportReport


# ---------- 阶段一：解析（纯函数，不碰数据库） ----------

def parse_workbook(file_bytes: bytes, default_category: str = "新需求") -> ParsedWorkbook:
    """解析 Excel 文件为内存数据结构。

    - 不访问数据库、无任何副作用
    - 返回 ParsedWorkbook：项目列表 + 报告（错误/警告/行数统计）
    - 文件级错误（无法读取/无数据 sheet）时 projects 为空、errors 非空
    """
    report = ImportReport()
    projects: list[ParsedProject] = []

    # 解析工作簿
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        report.errors.append(ImportError(
            row=0, sheet="(文件)", field="file",
            message=f"无法读取 Excel 文件: {e}",
        ))
        return ParsedWorkbook(projects, report)

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
        return ParsedWorkbook(projects, report)

    # 全局项目编号计数器：跨 sheet 连续编号（1,2,3...），避免两表编号冲突
    project_seq = 0

    for sheet_name, fmt in target_sheets:
        ws = wb[sheet_name]
        # 当前项目（阶段挂载用）：遇到项目行时更新
        current_project: ParsedProject | None = None

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
            status_explicit = status is not None and str(status).strip() != ""

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

                current_project = ParsedProject(
                    code=unique_code,
                    category=cat or default_category,
                    name=name_str,
                    owner=owner_str,
                    market=market_str or "国内",
                    status=status_str or "未开始",
                    plan_start=plan_start,
                    plan_end=plan_end,
                    remark=str(remark).strip() if remark else None,
                    status_explicit=status_explicit,
                )
                projects.append(current_project)
                report.projects_imported += 1

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
                sequence = int(seq_match.group(1)) if seq_match else len(current_project.phases) + 1

                # 进度：显式列优先（新格式），否则按状态推断
                progress_explicit = progress is not None and str(progress).strip() not in ("", "/")
                if progress_explicit:
                    try:
                        p = int(float(str(progress).strip()))
                        progress_val = max(0, min(100, p))
                    except ValueError:
                        progress_explicit = False
                        progress_val = 100 if status_str == "已完成" else (50 if status_str == "进行中" else 0)
                else:
                    progress_val = 100 if status_str == "已完成" else (50 if status_str == "进行中" else 0)

                current_project.phases.append(ParsedPhase(
                    name=phase_name,
                    phase_type=phase_type,
                    sequence=sequence,
                    plan_start=plan_start,
                    plan_end=plan_end,
                    actual_start=actual_start,
                    actual_end=actual_end,
                    status=status_str or "未开始",
                    progress=progress_val,
                    remark=str(remark).strip() if remark else None,
                    assignees=split_persons(assignees),
                    status_explicit=status_explicit,
                    progress_explicit=progress_explicit,
                ))
                report.phases_imported += 1

    return ParsedWorkbook(projects, report)


# ---------- 阶段二：落库 ----------

def import_parsed(db: Session, parsed: ParsedWorkbook) -> ImportReport:
    """把解析结果写入数据库（全量重置：先删所有 Project/Resource，保留 Template）。

    - parsed.report 中的 errors/warnings/统计原样保留，补充 resources_created
    - 返回 ImportReport，并存为最近报告供 GET /api/import/report 查询
    """
    report = parsed.report

    # 文件级错误（无法读取/无数据 sheet）：不落库，直接返回
    if not parsed.projects and report.errors:
        _set_last_report(report)
        return report

    # 全量重置：删 Project（级联）+ Resource（保留 Template）
    # 先解除 user→resource 引用：PG 外键约束下直接删被引用的 resource 会失败
    db.execute(update(User).values(resource_id=None).where(User.resource_id.is_not(None)))
    db.query(Project).delete()
    db.query(Resource).delete()
    db.flush()

    resource_cache: dict[str, Resource] = {}
    resources_created = 0

    for project in parsed.projects:
        proj = Project(
            code=project.code,
            category=project.category,
            name=project.name,
            owner=project.owner,
            market=project.market,
            status=project.status,
            plan_start=project.plan_start,
            plan_end=project.plan_end,
            remark=project.remark,
        )
        db.add(proj)
        db.flush()
        # 项目负责人也作为资源
        if project.owner:
            before = len(resource_cache)
            _get_or_create_resource(db, resource_cache, project.owner)
            if len(resource_cache) > before:
                resources_created += 1

        for ph in project.phases:
            phase = Phase(
                project_id=proj.id,
                phase_type=ph.phase_type,
                name=ph.name,
                sequence=ph.sequence,
                plan_start=ph.plan_start,
                plan_end=ph.plan_end,
                actual_start=ph.actual_start,
                actual_end=ph.actual_end,
                status=ph.status,
                progress=ph.progress,
                rework_count=0,
                remark=ph.remark,
            )
            db.add(phase)
            db.flush()

            # 拆分负责人，建/匹配 Resource 并关联
            if ph.assignees:
                assignee_resources = []
                for pname in ph.assignees:
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


def import_excel(db: Session, file_bytes: bytes, default_category: str = "新需求") -> ImportReport:
    """解析 Excel 文件并全量导入（兼容入口 = parse_workbook + import_parsed）。"""
    return import_parsed(db, parse_workbook(file_bytes, default_category))


# ---------- 阶段三：增量合并导入（默认模式） ----------

# 纯数字编号正则（合并模式新项目自动编号用）
_CODE_INT_RE = re.compile(r"^\d+$")


def _next_project_code(db: Session) -> str:
    """生成下一个项目编号：现有纯数字编号最大值 + 1（无则从 1 开始）。"""
    codes = db.scalars(select(Project.code)).all()
    nums = [int(c) for c in codes if c and _CODE_INT_RE.match(c)]
    return str(max(nums) + 1) if nums else "1"


# 阶段类型自然顺序（P1 最前 ... P8 最后），用于新增阶段的插入排序
_PHASE_TYPE_ORDER = {f"P{i}": i for i in range(1, 9)}


def _phase_type_rank(phase_type: str) -> int:
    return _PHASE_TYPE_ORDER.get(phase_type, 9)


def _merge_project(
    db: Session,
    project: Project,
    parsed_p: ParsedProject,
    resource_cache: dict[str, Resource],
    counters: dict[str, int],
    pending_links: list[tuple[str, str]],
) -> None:
    """合并同名项目：项目字段非空覆盖 + 阶段按类型匹配更新/自然序插入新增。

    counters: {"phases_created", "phases_updated"} 统计累加
    pending_links: 收集"新增阶段待关联依赖"（项目名, 阶段名）
    """
    # ---------- 项目字段：非空覆盖 ----------
    if parsed_p.owner:
        project.owner = parsed_p.owner
    if parsed_p.market:
        project.market = parsed_p.market
    if parsed_p.category:
        project.category = parsed_p.category
    if parsed_p.plan_start:
        project.plan_start = parsed_p.plan_start
    if parsed_p.plan_end:
        project.plan_end = parsed_p.plan_end
    if parsed_p.remark:
        project.remark = parsed_p.remark
    if parsed_p.status_explicit:
        project.status = parsed_p.status

    # ---------- 阶段合并 ----------
    existing = sorted(project.phases, key=lambda p: p.sequence)
    # 类型 → 阶段映射（同类型多个时只匹配第一个，其余文件同类型按新增处理）
    by_type: dict[str, Phase] = {}
    for ph in existing:
        by_type.setdefault(ph.phase_type, ph)

    for pp in parsed_p.phases:
        ph = by_type.get(pp.phase_type)
        if ph is not None:
            _merge_phase(db, ph, pp, resource_cache)
            counters["phases_updated"] += 1
        else:
            new_phase = _insert_phase(db, project.id, existing, pp, resource_cache)
            counters["phases_created"] += 1
            pending_links.append((project.name, pp.name))
            existing = sorted(project.phases, key=lambda p: p.sequence)
            by_type.setdefault(pp.phase_type, new_phase)

    # 负责人：项目负责人也作为资源（只增不删）
    if project.owner:
        _get_or_create_resource(db, resource_cache, project.owner)


def _merge_phase(db: Session, phase: Phase, pp: ParsedPhase, resource_cache: dict[str, Resource]) -> None:
    """更新已有阶段：文件非空字段覆盖；未填保留系统值。"""
    if pp.name:
        phase.name = pp.name
    if pp.plan_start:
        phase.plan_start = pp.plan_start
    if pp.plan_end:
        phase.plan_end = pp.plan_end
    if pp.actual_start:
        phase.actual_start = pp.actual_start
    if pp.actual_end:
        phase.actual_end = pp.actual_end
    if pp.status_explicit:
        phase.status = pp.status
    if pp.progress_explicit:
        phase.progress = pp.progress
    if pp.remark:
        phase.remark = pp.remark
    if pp.assignees:
        # 文件有值 → 覆盖负责人列表（resource 本身只增不删）
        assignees = []
        for pname in pp.assignees:
            assignees.append(_get_or_create_resource(db, resource_cache, pname))
        phase.assignees = assignees


def _insert_phase(
    db: Session,
    project_id: int,
    existing: list[Phase],
    pp: ParsedPhase,
    resource_cache: dict[str, Resource],
) -> Phase:
    """按阶段类型自然顺序插入新阶段（P1 最前 ... P8 最后），后续阶段序号顺延。返回新阶段。"""
    # 找插入点：第一个类型顺序大于新阶段的现有阶段
    pos = 0
    for ph in existing:
        if _phase_type_rank(ph.phase_type) > _phase_type_rank(pp.phase_type):
            break
        pos += 1

    # 插入点及之后的阶段序号顺延
    for ph in existing[pos:]:
        ph.sequence += 1

    if pos == 0:
        new_seq = 1
    else:
        new_seq = existing[pos - 1].sequence + 1

    phase = Phase(
        project_id=project_id,
        phase_type=pp.phase_type,
        name=pp.name,
        sequence=new_seq,
        plan_start=pp.plan_start,
        plan_end=pp.plan_end,
        actual_start=pp.actual_start,
        actual_end=pp.actual_end,
        status=pp.status,
        progress=pp.progress,
        rework_count=0,
        remark=pp.remark,
    )
    db.add(phase)
    db.flush()
    if pp.assignees:
        assignee_resources = []
        for pname in pp.assignees:
            assignee_resources.append(_get_or_create_resource(db, resource_cache, pname))
        phase.assignees = assignee_resources
    return phase


def import_merged(db: Session, parsed: ParsedWorkbook) -> ImportReport:
    """增量合并导入（默认模式）：新增 + 更新 + 保留，**不删除任何现有数据**。

    - 同名项目 → 项目字段非空覆盖 + 阶段按类型匹配更新/自然序插入新增
    - 新项目 → 创建（含 FS 串联依赖）
    - 已有依赖完全不动；同名项目的新增阶段不自动建依赖（报告提示待关联）
    """
    report = parsed.report

    # 文件级错误（无法读取/无数据 sheet）：不落库，直接返回
    if not parsed.projects and report.errors:
        _set_last_report(report)
        return report

    resource_cache: dict[str, Resource] = {}
    resources_created = 0
    counters = {"phases_created": 0, "phases_updated": 0}
    pending_links: list[tuple[str, str]] = []
    created_projects: list[Project] = []  # 新建项目（收尾建 FS 链）

    for parsed_p in parsed.projects:
        existing = db.scalars(select(Project).where(Project.name == parsed_p.name)).first()
        if existing:
            _merge_project(db, existing, parsed_p, resource_cache, counters, pending_links)
            report.projects_updated += 1
        else:
            # 新建项目：项目编号沿用系统自动编号（解析编号仅作行归类用，避免与现有项目冲突）
            proj = Project(
                code=_next_project_code(db),
                category=parsed_p.category,
                name=parsed_p.name,
                owner=parsed_p.owner,
                market=parsed_p.market,
                status=parsed_p.status,
                plan_start=parsed_p.plan_start,
                plan_end=parsed_p.plan_end,
                remark=parsed_p.remark,
            )
            db.add(proj)
            db.flush()
            if proj.owner:
                before = len(resource_cache)
                _get_or_create_resource(db, resource_cache, proj.owner)
                if len(resource_cache) > before:
                    resources_created += 1

            for pp in parsed_p.phases:
                phase = Phase(
                    project_id=proj.id,
                    phase_type=pp.phase_type,
                    name=pp.name,
                    sequence=pp.sequence,
                    plan_start=pp.plan_start,
                    plan_end=pp.plan_end,
                    actual_start=pp.actual_start,
                    actual_end=pp.actual_end,
                    status=pp.status,
                    progress=pp.progress,
                    rework_count=0,
                    remark=pp.remark,
                )
                db.add(phase)
                db.flush()
                if pp.assignees:
                    assignee_resources = []
                    for pname in pp.assignees:
                        before = len(resource_cache)
                        res = _get_or_create_resource(db, resource_cache, pname)
                        if len(resource_cache) > before:
                            resources_created += 1
                        assignee_resources.append(res)
                    phase.assignees = assignee_resources
            created_projects.append(proj)
            report.projects_created += 1
            counters["phases_created"] += len(parsed_p.phases)

    # 新建项目：按 sequence 建 FS 串联链（同名项目已有依赖不动）
    for proj in created_projects:
        phases = list(db.scalars(
            select(Phase).where(Phase.project_id == proj.id).order_by(Phase.sequence)
        ))
        _build_sequence_dependencies(db, phases)

    report.phases_created = counters["phases_created"]
    report.phases_updated = counters["phases_updated"]
    report.resources_created = resources_created
    report.pending_link_phases = [
        PendingLinkPhase(project_name=pn, phase_name=phn) for pn, phn in pending_links
    ]
    db.commit()

    _set_last_report(report)
    return report


# ---------- 导入前差异报告（预览） ----------

def build_preview(db: Session, parsed: ParsedWorkbook) -> ImportPreview:
    """基于解析结果 + 当前库生成差异报告（只读统计，无任何副作用）。

    包含两类信息：
    - 全量替换视角：existing（将被清空）/ incoming / match（同名对比）
    - 增量合并视角：created/updated/kept 明细 + 新增阶段待关联依赖提示
    """
    existing_projects = db.query(Project).count()
    existing_phases = db.query(Phase).count()
    existing_resources = db.query(Resource).count()

    incoming_projects = len(parsed.projects)
    incoming_phases = sum(len(p.phases) for p in parsed.projects)

    # 同名项目对比（防传错文件）
    existing_names = set(db.scalars(select(Project.name)).all())
    incoming_names = {p.name for p in parsed.projects if p.name}
    matched = len(incoming_names & existing_names)
    new = len(incoming_names - existing_names)
    missing = len(existing_names - incoming_names)

    def _preview(p: ParsedProject) -> PreviewProject:
        return PreviewProject(
            name=p.name,
            market=p.market,
            category=p.category,
            phases=len(p.phases),
        )

    # 项目概览（前 20 个）
    projects_preview = [_preview(p) for p in parsed.projects[:20]]

    # 增量合并明细
    existing_proj_map = {
        p.name: p for p in db.scalars(select(Project)).all()
    }
    created_projects = [_preview(p) for p in parsed.projects if p.name not in existing_proj_map]
    updated_projects = [_preview(p) for p in parsed.projects if p.name in existing_proj_map]

    # 阶段统计与待关联提示（基于现有同名项目的阶段类型）
    phases_created = 0
    phases_updated = 0
    pending: list[PendingLinkPhase] = []
    for p in parsed.projects:
        ep = existing_proj_map.get(p.name)
        if ep is None:
            phases_created += len(p.phases)  # 新项目全部阶段为新增
            continue
        existing_types = {ph.phase_type for ph in ep.phases}
        for pp in p.phases:
            if pp.phase_type in existing_types:
                phases_updated += 1
            else:
                phases_created += 1
                pending.append(PendingLinkPhase(project_name=p.name, phase_name=pp.name))

    return ImportPreview(
        existing=ImportExistingCounts(
            projects=existing_projects,
            phases=existing_phases,
            resources=existing_resources,
        ),
        incoming=ImportIncomingCounts(
            projects=incoming_projects,
            phases=incoming_phases,
        ),
        match=ProjectMatchInfo(matched=matched, new=new, missing=missing),
        errors=list(parsed.report.errors),
        warnings=list(parsed.report.warnings),
        projects_preview=projects_preview,
        created_projects=created_projects,
        updated_projects=updated_projects,
        kept_count=missing,
        phases_created=phases_created,
        phases_updated=phases_updated,
        pending_link_phases=pending,
    )


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
