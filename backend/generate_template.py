"""生成项目经理填报 Excel 模板。

产出文件：docs/项目填报模板.xlsx
- Sheet1「填报说明」：字段说明 + 数据验证规则
- Sheet2「国内项目」：国内项目填报区
- Sheet3「海外项目」：海外项目填报区
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "项目填报模板.xlsx"

# ---------- 常量 ----------
HEADERS = [
    "项目编号",  # A
    "项目类目",  # B
    "项目名称",  # C
    "项目负责人",  # D
    "市场",  # E
    "计划开始",  # F
    "计划结束",  # G
    "实际开始",  # H
    "实际结束",  # I
    "阶段类型",  # J
    "阶段负责人",  # K
    "交接人",  # L
    "阶段状态",  # M
    "阶段进度",  # N
    "备注",  # O
]

# 列宽
COL_WIDTHS = [12, 10, 30, 12, 8, 13, 13, 13, 13, 14, 20, 10, 10, 8, 20]

# 样式
HEADER_FILL = PatternFill(start_color="001529", end_color="001529", fill_type="solid")
HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="微软雅黑", size=14, bold=True, color="001529")
BODY_FONT = Font(name="微软雅黑", size=10)
NOTE_FONT = Font(name="微软雅黑", size=9, color="666666")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center")
WRAP = Alignment(wrap_text=True, vertical="top")

# 下拉选项
CATEGORIES = '"新需求,量产,定制,改造"'
MARKETS = '"国内,海外"'
PHASE_TYPES = '"P1 需求评估,P2 配置评估,P3 模块选型,P4 工业设计,P5 结构设计,P6 样机打样,P7 联调测试,P8 交付"'
PHASE_STATUSES = '"未开始,进行中,已完成,延期,已搁置"'


def _style_sheet(ws, data_rows=200):
    """统一设置工作表格式。"""
    COLS = len(HEADERS)  # 15

    # 列宽
    for i, w in enumerate(COL_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # 冻结表头
    ws.freeze_panes = "A3"

    LAST_COL = get_column_letter(COLS)

    # ---------- 第 1 行：标题 ----------
    ws.merge_cells(f"A1:{LAST_COL}1")
    ws["A1"].value = "智能终端研发项目管理平台 — 项目填报模板"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # ---------- 第 2 行：列头 ----------
    ws.row_dimensions[2].height = 22
    for col, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    # ---------- 数据行 ----------
    for r in range(3, data_rows + 3):
        ws.row_dimensions[r].height = 22
        for c in range(1, COLS + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            if c in (1, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14):
                cell.alignment = CENTER

    last = f"{data_rows + 2}"

    # ---------- 数据验证 ----------
    # 类目 (B)
    dv = DataValidation(type="list", formula1=CATEGORIES, allow_blank=True)
    dv.error = "请从下拉列表中选择"
    ws.add_data_validation(dv); dv.add(f"B3:B{last}")

    # 市场 (E)
    dv = DataValidation(type="list", formula1=MARKETS, allow_blank=True)
    ws.add_data_validation(dv); dv.add(f"E3:E{last}")

    # 阶段类型 (J)
    dv = DataValidation(type="list", formula1=PHASE_TYPES, allow_blank=True)
    dv.error = "请从下拉列表中选择阶段类型"
    ws.add_data_validation(dv); dv.add(f"J3:J{last}")

    # 阶段状态 (M)
    dv = DataValidation(type="list", formula1=PHASE_STATUSES, allow_blank=True)
    ws.add_data_validation(dv); dv.add(f"M3:M{last}")

    # 阶段进度 (N) — 0-100
    dv = DataValidation(type="whole", operator="between", formula1="0", formula2="100")
    dv.error = "进度请填 0-100"
    ws.add_data_validation(dv); dv.add(f"N3:N{last}")

    # 日期 (F-I) — 4 列日期
    dv = DataValidation(type="date", operator="greaterThan", formula1="2024-01-01")
    dv.error = "请填入有效日期"
    ws.add_data_validation(dv); dv.add(f"F3:I{last}")

    # 提示注释
    ws.cell(row=3, column=1).comment = openpyxl.comments.Comment(
        "项目行填纯数字（如 1、2）\n阶段行填 项目号-序号（如 1-1）\n空行自动跳过",
        "系统提示"
    )


def _create_instruction_sheet(wb):
    """创建填报说明 Sheet。"""
    ws = wb.active
    ws.title = "填报说明"

    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 50

    title = ws.cell(row=2, column=2, value="📋 填报说明")
    title.font = TITLE_FONT

    instructions = [
        ("填写规则", ""),
        ("", "1. 项目行：项目编号填纯数字（如 1、2、3），其余列按实际情况填写。"),
        ("", "2. 阶段行：项目编号填「项目号-序号」（如 1-1、2-3）。阶段类型为必填下拉。"),
        ("", "3. 空行（项目编号和项目名称均为空）会被自动跳过，可用于分隔不同项目。"),
        ("", "4. 市场列已区分国内/海外，所有项目填在同一个 Sheet 即可。"),
    ("", ""),
    ("阶段依赖关系", ""),
    ("", "导入后，系统会自动按阶段序号生成 FS（完成-开始）依赖链："),
    ("", "　例如项目 1 有阶段 1-1→1-2→1-3→1-4，导入后自动串联依赖。"),
    ("", "如需更复杂的依赖类型（SS 并行 / 跨阶段），请在系统甘特图中手动调整。"),
    ("", ""),
        ("字段说明", ""),
        ("项目编号", "必填。项目行纯数字，阶段行数字-数字（如 1-1）。"),
        ("项目类目", "必填。下拉选择：新需求 / 量产 / 定制 / 改造。"),
        ("项目名称", "必填。项目的完整名称。"),
        ("项目负责人", "必填。负责该项目的项目经理姓名。"),
        ("市场", "必填。下拉选择：国内 / 海外。"),
        ("计划开始/结束", "日期格式 YYYY-MM-DD（如 2026-07-01）。"),
        ("实际开始/结束", "日期格式 YYYY-MM-DD。项目行不填，阶段行按实际情况。"),
        ("阶段类型", "阶段行必填。下拉选择：P1 需求评估 ~ P8 交付。"),
        ("阶段负责人", "多人用空格或顿号分隔（如「张三 李四」）。"),
        ("交接人", "阶段行可选。该阶段的交接对象。"),
        ("阶段状态", "阶段行，下拉选择：未开始 / 进行中 / 已完成 / 延期 / 已搁置。"),
        ("阶段进度", "阶段行，填 0-100 的整数。"),
        ("备注", "可选。任何补充说明。"),
        ("", ""),
        ("导入方式", ""),
        ("", "在平台「项目列表」页面点击「导入 Excel」，选择本文件即可。"),
        ("", "导入前会自动清空现有数据（模板不受影响），支持重复导入。"),
        ("", f"模板生成日期：{date.today().isoformat()}"),
    ]

    for i, (field, desc) in enumerate(instructions):
        r = i + 4
        cell_b = ws.cell(row=r, column=2, value=field)
        cell_c = ws.cell(row=r, column=3, value=desc)
        cell_b.font = Font(name="微软雅黑", size=10, bold=bool(field and desc))
        cell_c.font = NOTE_FONT if not field else Font(name="微软雅黑", size=10)


def _create_data_sheet(wb, title, sample_rows=3):
    """创建数据填报 Sheet。"""
    ws = wb.create_sheet(title=title)
    _style_sheet(ws)

    # 样例数据
    if sample_rows:
        samples = [
            # 项目 1：招标研发 - col: 编号,类目,名称,负责人,市场,计划开始,计划结束,实际开始,实际结束,阶段类型,阶段负责人,交接人,阶段状态,进度,备注
            [1, "新需求", "示例：XX银行自助终端TCM-001", "张三", "国内", "2026-07-01", "2026-09-30", "", "", "", "", "", "", "", ""],
            ["1-1", "", "", "", "", "2026-07-01", "2026-07-05", "2026-07-01", "2026-07-05", "P4 工业设计", "李四", "", "已完成", 100, ""],
            ["1-2", "", "", "", "", "2026-07-06", "2026-07-20", "2026-07-06", "", "P5 结构设计", "李四 王五", "赵六", "进行中", 60, ""],
            ["1-3", "", "", "", "", "2026-07-21", "2026-09-30", "", "", "P7 联调测试", "王五", "", "未开始", 0, "待启动"],
            # 空行
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            # 项目 2：量产 - 海外
            [2, "量产", "示例：海外侧柜量产RS-028", "张三", "海外", "2026-08-01", "2026-12-31", "", "", "", "", "", "", "", ""],
            ["2-1", "", "", "", "", "2026-08-01", "2026-08-30", "", "", "P5 结构设计", "钱七", "", "未开始", 0, ""],
        ]
        for i, row in enumerate(samples):
            r = i + 3
            for c, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=val)
                cell.font = BODY_FONT


def main():
    wb = openpyxl.Workbook()

    _create_instruction_sheet(wb)
    _create_data_sheet(wb, "项目填报")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(OUTPUT))
    print(f"✅ 模板已生成：{OUTPUT}")
    print(f"   Sheet1「填报说明」— 字段说明 + 导入指引")
    print(f"   Sheet2「项目填报」— 200 行填报区 + 7 项下拉验证")


if __name__ == "__main__":
    main()
