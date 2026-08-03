"""Excel 导入器测试。

分两类：
1. 单元测试：清洗工具函数（parse_cell_date / split_persons / classify_row / map_phase_type）
2. 端到端测试：用真实 Excel 文件做导入（文件缺失则 skip）

真实文件路径：~/Desktop/整机项目进度及计划情况统计-0720.xlsx
预期：国内 8 + 海外 10 = 18 项目，57 阶段。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from app.models import Dependency, Phase, Project, Resource
from app.schemas.import_report import ImportReport
from app.services.excel_importer import (
    PHASE_NAME_TO_TYPE,
    classify_row,
    import_excel,
    map_phase_type,
    parse_cell_date,
    split_persons,
)

_REAL_EXCEL = Path.home() / "Desktop" / "整机项目进度及计划情况统计-0720.xlsx"


# ---------- 单元测试：清洗函数 ----------

def _empty_report() -> ImportReport:
    return ImportReport()


def test_classify_row():
    assert classify_row("1", "项目A") == "project"
    assert classify_row("1-1", "工业设计") == "phase"
    assert classify_row("2-3", "结构设计") == "phase"
    assert classify_row(None, None) == "skip"           # 空行
    assert classify_row("【状态图例】", None) == "skip"  # 备注行
    assert classify_row("未发货样机", "长文本...") == "skip"


def test_split_persons_multi_space():
    """多空格分隔的多人字段。"""
    assert split_persons("苏树冲             陆永杰") == ["苏树冲", "陆永杰"]


def test_split_persons_variants():
    """逗号（中英文）、换行、"/" 占位符。"""
    assert split_persons("曹俊杰,宋海波") == ["曹俊杰", "宋海波"]
    assert split_persons("曹俊杰，宋海波") == ["曹俊杰", "宋海波"]
    assert split_persons("曹俊杰\n宋海波") == ["曹俊杰", "宋海波"]
    assert split_persons("/") == []
    assert split_persons(None) == []
    assert split_persons("") == []
    # 去重
    assert split_persons("张三 张三") == ["张三"]


def test_parse_cell_date_datetime():
    """datetime 对象 → date。"""
    report = _empty_report()
    d = parse_cell_date(datetime(2026, 7, 1, 12, 0), 1, "国内", "plan_start", report)
    assert d == date(2026, 7, 1)
    assert report.warnings == []  # 正常解析无 warning


def test_parse_cell_date_anomaly_text():
    """文本异常（'2026/-/--'）→ None + warning。"""
    report = _empty_report()
    d = parse_cell_date("2026/-/--", 31, "国内", "plan_end", report)
    assert d is None
    assert len(report.warnings) == 1
    assert "无法解析日期" in report.warnings[0].message


def test_parse_cell_date_none():
    assert parse_cell_date(None, 1, "x", "f", _empty_report()) is None
    assert parse_cell_date("", 1, "x", "f", _empty_report()) is None


def test_map_phase_type_known():
    """文档 §5.3 映射表内的阶段名。"""
    report = _empty_report()
    assert map_phase_type("工业设计", 1, "国内", report) == "P4"
    assert map_phase_type("结构设计", 1, "国内", report) == "P5"
    assert map_phase_type("样机打样", 1, "国内", report) == "P6"
    assert map_phase_type("联调测试", 1, "国内", report) == "P7"
    assert map_phase_type("POC及投标", 1, "国内", report) == "P8"
    assert map_phase_type("需求分析", 1, "国内", report) == "P1"
    assert report.errors == []


def test_map_phase_type_unknown_records_error():
    """不在映射表的阶段名 → None + error。"""
    report = _empty_report()
    # 用真正不存在的阶段名（扩充映射表后已覆盖实际 Excel 的所有变体）
    assert map_phase_type("完全不存在的阶段XYZ", 1, "海外", report) is None
    assert map_phase_type("未知阶段", 1, "海外", report) is None
    assert len(report.errors) == 2


def test_phase_name_mapping_table_completeness():
    """验证映射表覆盖了文档 §5.3 原表 + 实际 Excel 的 5 个变体。"""
    # §5.3 原表的 18 个
    expected_keys = {
        "工业设计", "结构设计", "整机设计", "样机打样",
        "联调测试", "测试", "POC及投标",
        "需求分析", "需求评估", "配置评估", "模块选型",
        "直接投料", "图纸归档", "归档", "BOM制作与激活",
        "首批生产保障", "投料", "发货",
    }
    # 实际 Excel 的 6 个变体（扩充部分）
    expanded_keys = {
        "测试与发货", "样机打样（1台）", "归档（归档后再投料）",
        "直接投料，BOM制作与激活", "直接投料，激活时间", "交付",
    }
    all_keys = expected_keys | expanded_keys
    assert all_keys <= set(PHASE_NAME_TO_TYPE.keys()), (
        f"映射表缺少: {all_keys - set(PHASE_NAME_TO_TYPE.keys())}"
    )


# ---------- 端到端测试：真实 Excel 导入 ----------

@pytest.fixture()
def real_excel_bytes():
    if not _REAL_EXCEL.exists():
        pytest.skip(f"真实 Excel 文件不存在: {_REAL_EXCEL}")
    return _REAL_EXCEL.read_bytes()


def test_import_real_excel(client, db_session, real_excel_bytes):
    """导入真实 Excel：应得到 18 项目（国内 8 + 海外 10）。"""
    resp = client.post(
        "/api/import/excel",
        files={"file": ("整机项目进度及计划情况统计-0720.xlsx", real_excel_bytes)},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["projects_imported"] == 18
    assert report["phases_imported"] == 57

    # 校验市场分布
    projects = client.get("/api/projects").json()
    domestic = [p for p in projects if p["market"] == "国内"]
    overseas = [p for p in projects if p["market"] == "海外"]
    assert len(domestic) == 8
    assert len(overseas) == 10
    # 项目类目默认为"新需求"
    assert all(p["category"] == "新需求" for p in projects)


def test_import_idempotent(client, db_session, real_excel_bytes):
    """重复导入幂等：第二次导入后仍是 18 项目。"""
    for _ in range(2):
        resp = client.post(
            "/api/import/excel",
            files={"file": ("test.xlsx", real_excel_bytes)},
        )
        assert resp.status_code == 200
    assert resp.json()["projects_imported"] == 18
    assert len(client.get("/api/projects").json()) == 18


def test_import_creates_resources(client, db_session, real_excel_bytes):
    """多人字段被正确拆分为独立人员。"""
    client.post(
        "/api/import/excel",
        files={"file": ("test.xlsx", real_excel_bytes)},
    )
    resources = client.get("/api/resources").json()
    # 至少有若干人员
    assert len(resources) >= 10
    names = {r["name"] for r in resources}
    # 验证某些已知人员存在（基于数据探查）
    assert "曹俊杰" in names or "何昊" in names


def test_import_date_anomalies_recorded_as_warnings(client, db_session, real_excel_bytes):
    """'2026/-/--' 类日期被记为 warning，对应 plan_end/plan_start 为 null。"""
    resp = client.post(
        "/api/import/excel",
        files={"file": ("test.xlsx", real_excel_bytes)},
    )
    report = resp.json()
    # 数据探查发现多处日期异常，导入时被正确捕获为 warning
    assert len(report["warnings"]) >= 3
    # 至少有一个阶段/项目的日期被设为 null（埃塞 AWASH 项目 plan_start='2026/-/--'）
    has_null_date = False
    for p in client.get("/api/projects").json():
        if p["plan_start"] is None or p["plan_end"] is None:
            has_null_date = True
            break
    assert has_null_date


def test_import_unmappable_phase_names_recorded_as_errors(client, db_session, real_excel_bytes):
    """扩充映射表后，实际 Excel 的所有阶段名都能映射，无 error。"""
    resp = client.post(
        "/api/import/excel",
        files={"file": ("test.xlsx", real_excel_bytes)},
    )
    report = resp.json()
    # 映射表已覆盖所有实际阶段名（含 测试与发货、样机打样（1台）等变体）
    assert len(report["errors"]) == 0
    # 阶段总数仍是 57
    assert report["phases_imported"] == 57


def test_import_builds_dependencies(client, db_session, real_excel_bytes):
    """导入后每个项目的阶段按 sequence 建了 FS 依赖。"""
    client.post(
        "/api/import/excel",
        files={"file": ("test.xlsx", real_excel_bytes)},
    )
    # 取第一个项目的甘特图，验证有 link
    pid = client.get("/api/projects").json()[0]["id"]
    gantt = client.get(f"/api/projects/{pid}/gantt").json()
    assert len(gantt["links"]) >= 1
    assert all(l["type"] == "0" for l in gantt["links"])  # FS


def test_import_report_endpoint(client, db_session, real_excel_bytes):
    """GET /api/import/report 能取到最近一次导入报告。"""
    client.post(
        "/api/import/excel",
        files={"file": ("test.xlsx", real_excel_bytes)},
    )
    resp = client.get("/api/import/report")
    assert resp.status_code == 200
    assert resp.json()["projects_imported"] == 18


def test_import_report_404_when_none(client, db_session):
    """无导入记录时 GET /api/import/report 返回 404。"""
    resp = client.get("/api/import/report")
    assert resp.status_code == 404


def test_import_rejects_non_excel(client, db_session):
    """非 Excel 文件被拒绝。"""
    resp = client.post(
        "/api/import/excel",
        files={"file": ("test.txt", b"hello")},
    )
    assert resp.status_code == 400


# ---------- 直接调用 import_excel 的单元测试（构造内存 Excel） ----------

def test_import_excel_direct_with_constructed_workbook(client, db_session):
    """构造一个最小 Excel，直接测导入逻辑（不依赖真实文件）。"""
    import openpyxl
    from app.services.excel_importer import import_excel

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "项目情况统计-国内"
    # 表头 2 行
    ws.cell(1, 1, "项目编号")
    ws.cell(2, 9, "1")  # 第 2 行的月份表头（无意义，模拟）
    # 项目 1
    ws.cell(3, 1, "1")
    ws.cell(3, 2, "工行招标")
    ws.cell(3, 3, "测试项目")
    ws.cell(3, 4, "张三")
    ws.cell(3, 5, datetime(2026, 7, 1))
    ws.cell(3, 6, datetime(2026, 8, 1))
    ws.cell(3, 7, "进行中")
    # 阶段 1-1
    ws.cell(4, 1, "1-1")
    ws.cell(4, 2, "阶段A")
    ws.cell(4, 3, "工业设计")
    ws.cell(4, 4, "李四 王五")
    ws.cell(4, 5, datetime(2026, 7, 1))
    ws.cell(4, 6, datetime(2026, 7, 10))
    ws.cell(4, 7, "已完成")
    # 阶段 1-2
    ws.cell(5, 1, "1-2")
    ws.cell(5, 2, "阶段B")
    ws.cell(5, 3, "结构设计")
    ws.cell(5, 4, "李四")
    ws.cell(5, 5, datetime(2026, 7, 11))
    ws.cell(5, 6, datetime(2026, 7, 30))
    ws.cell(5, 7, "进行中")

    import io
    buf = io.BytesIO()
    wb.save(buf)

    from app.database import SessionLocal
    # 用 TestClient 已注入的 db_session
    report = import_excel(db_session, buf.getvalue())
    assert report.projects_imported == 1
    assert report.phases_imported == 2

    # 验证人员拆分：李四、王五、张三
    resources = list(db_session.query(Resource))
    names = {r.name for r in resources}
    assert {"张三", "李四", "王五"} <= names

    # 验证依赖：1-1 → 1-2 FS
    deps = list(db_session.query(Dependency))
    assert len(deps) == 1
    assert deps[0].type == "FS"

    # 验证 phase_type 映射
    phases = list(db_session.query(Phase).order_by(Phase.sequence))
    assert phases[0].phase_type == "P4"  # 工业设计
    assert phases[1].phase_type == "P5"  # 结构设计
