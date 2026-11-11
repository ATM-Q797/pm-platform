"""专项导入域测试（SPECIAL_PROJECT §五·B）：常规导入隔离 + 专项导入 + special 模式解析。

覆盖：常规 replace/merge/preview 不动专项、专项导入重置专项域与 ZX 系列编号、
旧格式专项、导入权限、special 模式自定义阶段类型解析。
自 test_special_project.py 拆出（文件分层 >800 行硬档处置）——用例体逐字未动。
"""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

import openpyxl

from app.models import Phase, Project, Resource
from app.services.excel_importer import parse_workbook

from .test_special_project import (
    _login,
    _mk_phase,
    _mk_project,
    _mk_resource,
    _mk_user,
    _today,
)
# ---- §七 用例 13/14：常规导入隔离 + 专项导入（SPECIAL_PROJECT §五·B，评审 🔴 处置）----


def _make_workbook(rows: list[list]) -> bytes:
    """按 14 列新格式构造 Excel（与 test_merge_import 同构）。每行: [编号, 类目, 名称,
    负责人, 市场, 阶段类型, 计划开始, 计划结束, 实际开始, 实际结束,
    阶段负责人, 阶段状态, 阶段进度, 备注]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "项目填报"
    headers = ["项目编号", "项目类目", "项目名称", "项目负责人", "市场", "阶段类型",
               "计划开始", "计划结束", "实际开始", "实际结束",
               "阶段负责人", "阶段状态", "阶段进度", "备注"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    for i, row in enumerate(rows):
        for c, v in enumerate(row, 1):
            ws.cell(3 + i, c, v)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_old_workbook(rows: list[list]) -> bytes:
    """按 8 列旧格式构造 Excel。每行: [编号, 类目, 名称, 负责人, 计划开始, 计划结束, 状态, 交接人]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "项目情况统计-海外"
    headers = ["项目编号", "项目类目", "项目名称", "负责人", "计划开始", "计划结束", "状态", "交接人"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    for i, row in enumerate(rows):
        for c, v in enumerate(row, 1):
            if v is not None:
                ws.cell(3 + i, c, v)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _mk_special_with_phase(db_session, name: str) -> tuple[Project, Phase, Resource]:
    """专项项目 + 1 阶段（assignee 关联到独立 Resource），返回 (project, phase, resource)。"""
    sp = _mk_project(db_session, name, is_special=True)
    r = _mk_resource(db_session, f"{name}-执行人")
    ph = _mk_phase(db_session, sp, f"{name}-阶段", _today(), _today() + timedelta(days=30))
    ph.assignees = [r]
    return sp, ph, r


def test_special_mode_custom_type_without_code(client, db_session):
    """用户 2026-08-28 真实表《自研机械锁钥匙锁项目填报总表》：阶段行无编号、
    阶段类型列即阶段名（自定义类型）→ special 模式全识别（0 警告）。"""
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "专项测试"
    ws.append(["智能终端研发项目管理平台 — 项目填报模板"])  # 标题行（第 1 行，_DATA_START_ROW=3）
    ws.append(["项目编号", "项目类目", "项目名称", "项目负责人", "市场", "阶段类型",
               "计划开始", "计划结束", "实际开始", "实际结束", "阶段负责人", "阶段状态", "阶段进度", "备注"])
    ws.append([1, "新需求", "自研项目A", "张三", "海外通用", None,
               "2026-01-01", "2026-12-31", None, None, None, "进行中", None, None])
    for i, t in enumerate(["项目立项", "一样图纸设计", "VDS认证送样测试"], start=1):
        ws.append([None, None, None, None, None, t,
                   f"2026-0{i}-01", f"2026-0{i}-28", None, None, "张三", "未开始", 0, None])
    buf = BytesIO()
    wb.save(buf)
    parsed = parse_workbook(buf.getvalue(), special=True)
    assert len(parsed.report.errors) == 0
    assert len(parsed.report.warnings) == 0  # 无编号 + 自定义类型行不再被跳过
    assert len(parsed.projects) == 1
    assert [ph.phase_type for ph in parsed.projects[0].phases] == [
        "项目立项", "一样图纸设计", "VDS认证送样测试"]
    assert [ph.name for ph in parsed.projects[0].phases] == [
        "项目立项", "一样图纸设计", "VDS认证送样测试"]  # 名称兜底 = 类型列
    # 常规模式该表仍跳过（自定义类型不属于常规项目域）
    parsed2 = parse_workbook(buf.getvalue())
    assert len(parsed2.report.warnings) == 3


def test_13_regular_replace_preserves_special(client, db_session):
    """用例 13a：常规全量导入（replace）后专项项目（阶段/assignee/Resource）原样保留；报告含专项提示。"""
    sp, sp_ph, sp_res = _mk_special_with_phase(db_session, "专项保留项目")
    # 常规项目 + 仅被常规引用的 Resource（应被清掉）
    np = _mk_project(db_session, "常规旧项目")
    np_res = _mk_resource(db_session, "常规旧人员")
    _mk_phase(db_session, np, "常规旧阶段", _today(), _today() + timedelta(days=10)).assignees = [np_res]
    db_session.commit()

    data = _make_workbook([
        [1, "新需求", "常规新项目", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
    ])
    resp = client.post("/api/import/excel", files={"file": ("t.xlsx", data)},
                       params={"mode": "replace"})
    assert resp.status_code == 200, resp.text
    report = resp.json()

    # 报告注明专项不受影响
    assert any("专项项目 1 个不受影响" in w["message"] for w in report["warnings"])

    # 专项项目原样保留（id/阶段/assignee Resource 均未动）
    db_session.expire_all()
    assert db_session.query(Project).filter(Project.is_special.is_(True)).count() == 1
    assert db_session.query(Phase).filter(Phase.id == sp_ph.id).count() == 1
    kept_ph = db_session.query(Phase).filter(Phase.id == sp_ph.id).one()
    assert [r.name for r in kept_ph.assignees] == ["专项保留项目-执行人"]
    assert db_session.query(Resource).filter(Resource.id == sp_res.id).count() == 1

    # 常规域被清空重建：旧常规项目/阶段/人员没了，新项目在（专项仍保留）
    assert db_session.query(Project).filter(Project.name == "常规旧项目").count() == 0
    assert db_session.query(Resource).filter(Resource.name == "常规旧人员").count() == 0
    names = [p.name for p in db_session.query(Project).filter(Project.is_special.is_(False)).all()]
    assert names == ["常规新项目"]


def test_13_regular_merge_not_into_special(client, db_session):
    """用例 13b：常规合并导入与专项同名 → 不合并进专项（新建常规项目），专项原样。"""
    sp, sp_ph, _ = _mk_special_with_phase(db_session, "同名专项")
    db_session.commit()

    data = _make_workbook([
        [1, "新需求", "同名专项", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
        ["1-1", "", "", "", "", "工业设计", "2026-07-01", "2026-07-10", "", "", "李四", "进行中", 50, ""],
    ])
    resp = client.post("/api/import/excel", files={"file": ("t.xlsx", data)},
                       params={"mode": "merge"})
    assert resp.status_code == 200, resp.text
    report = resp.json()

    # 不合并进专项 → 视为新建常规项目
    assert report["projects_created"] == 1
    assert report["projects_updated"] == 0

    # 专项原样（阶段未被合并/新增）
    db_session.expire_all()
    assert db_session.query(Project).filter(Project.name == "同名专项", Project.is_special.is_(True)).count() == 1
    assert db_session.query(Phase).filter(Phase.id == sp_ph.id).count() == 1

    # 新建的常规项目（同名）存在
    reg = db_session.query(Project).filter(Project.is_special.is_(False), Project.name == "同名专项").first()
    assert reg is not None
    assert len(reg.phases) == 1


def test_13_regular_preview_excludes_special(client, db_session):
    """用例 13c：常规预览专项不计入 existing/matched/kept（专项域数据全不出现）。"""
    sp, sp_ph, sp_res = _mk_special_with_phase(db_session, "专项预览项目")
    np = _mk_project(db_session, "常规预览项目")
    np_res = _mk_resource(db_session, "常规预览人员")
    _mk_phase(db_session, np, "常规预览阶段", _today(), _today() + timedelta(days=10)).assignees = [np_res]
    db_session.commit()

    # 文件只含一个全新项目（防传错对比：matched=0/new=1/missing=1，全部常规域口径）
    data = _make_workbook([
        [1, "新需求", "常规新项目", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
    ])
    resp = client.post("/api/import/preview", files={"file": ("t.xlsx", data)})
    assert resp.status_code == 200, resp.text
    pv = resp.json()

    # existing：仅常规域（专项项目/阶段/专项引用 Resource 不计入"将被清空"）
    assert pv["existing"]["projects"] == 1
    assert pv["existing"]["phases"] == 1
    assert pv["existing"]["resources"] == 1  # 仅常规预览人员；专项执行人保留

    # match/kept 均不含专项
    assert pv["match"] == {"matched": 0, "new": 1, "missing": 1}
    assert pv["kept_count"] == 1
    assert all(p["name"] != "专项预览项目" for p in pv["projects_preview"])


def test_13_special_numeric_code_does_not_block_replace(client, db_session):
    """编号冲突回归（实测 PG 复现）：专项项目占用纯数字编号 '1' 时，
    常规全量导入续编不撞唯一约束 project.code，专项保留。"""
    sp = _mk_project(db_session, "编号专项", is_special=True)
    sp.code = "1"  # 专项导入的文件行号编号方式（'1'..'N'）
    db_session.commit()

    data = _make_workbook([
        [1, "新需求", "常规新项目", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
    ])
    resp = client.post("/api/import/excel", files={"file": ("t.xlsx", data)},
                       params={"mode": "replace"})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    sp2 = db_session.query(Project).filter(Project.name == "编号专项").one()
    assert sp2.code == "1"
    reg = db_session.query(Project).filter(Project.name == "常规新项目").one()
    assert reg.code == "2"  # 续编：现有最大编号 + 1


def test_14_special_import_resets_special_domain(client, db_session):
    """用例 14a：专项导入全量重置专项域——旧专项删、新专项按文件建 is_special=True、
    阶段类型自由文本直存、FS 链建好、常规项目不受影响；最近报告槽位更新。"""
    old_sp, old_ph, _ = _mk_special_with_phase(db_session, "旧专项")
    np = _mk_project(db_session, "常规不动项目")
    np_ph = _mk_phase(db_session, np, "常规阶段", _today(), _today() + timedelta(days=10))
    db_session.commit()

    data = _make_workbook([
        [1, "专项类目", "新专项A", "专项负责人", "拉美区", "", "2026-07-01", "2026-09-30", "", "", "", "", "", ""],
        ["1-1", "", "", "", "", "电磁兼容测试", "2026-07-01", "2026-07-20", "", "", "专项执行人", "进行中", 30, "专项备注"],
        ["1-2", "", "", "", "", "可靠性验证", "2026-07-21", "2026-08-10", "", "", "专项执行人", "未开始", 0, ""],
    ])
    resp = client.post("/api/import/special", files={"file": ("t.xlsx", data)})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["projects_imported"] == 1
    assert report["phases_imported"] == 2
    assert report["errors"] == []

    # 旧专项删除（含阶段级联），新专项 is_special=True、阶段类型原样存储
    db_session.expire_all()
    assert db_session.query(Project).filter(Project.name == "旧专项").count() == 0
    assert db_session.query(Phase).filter(Phase.name == "旧专项-阶段").count() == 0
    sp = db_session.query(Project).filter(Project.name == "新专项A").first()
    assert sp is not None and sp.is_special is True
    assert sp.owner == "专项负责人" and sp.market == "拉美区" and sp.category == "专项类目"
    ph1 = next(p for p in sp.phases if p.sequence == 1)
    ph2 = next(p for p in sp.phases if p.sequence == 2)
    assert ph1.phase_type == "电磁兼容测试"
    assert ph2.phase_type == "可靠性验证"
    assert ph1.remark == "专项备注"
    # assignee 全局复用 Resource（同名人员不重复建）
    res = db_session.query(Resource).filter(Resource.name == "专项执行人").one()
    assert res.id == ph1.assignees[0].id == ph2.assignees[0].id
    # FS 串联链建好（2 阶段 1 条链）
    from app.models import Dependency
    deps = db_session.query(Dependency).filter(
        Dependency.from_phase_id == ph1.id, Dependency.to_phase_id == ph2.id
    ).count()
    assert deps == 1

    # 常规项目完全不受影响（id/阶段原样）
    np2 = db_session.query(Project).filter(Project.name == "常规不动项目").one()
    assert np2.is_special is False
    assert db_session.query(Phase).filter(Phase.id == np_ph.id).count() == 1

    # 最近报告槽位 = 专项报告
    last = client.get("/api/import/report").json()
    assert last["projects_imported"] == 1 and last["phases_imported"] == 2


def test_14_special_import_uses_zx_series(client, db_session):
    """专项导入取号：专项走独立 ZX 系列，不占用普通数字编号（用户 2026-10-30 规则）。"""
    np = _mk_project(db_session, "常规占号")
    np.code = "1"
    db_session.commit()

    data = _make_workbook([
        [1, "新需求", "专项新项目", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
    ])
    resp = client.post("/api/import/special", files={"file": ("t.xlsx", data)})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    sp = db_session.query(Project).filter(Project.name == "专项新项目").one()
    assert sp.is_special is True
    assert sp.code == "ZX001"  # 专项独立系列，不挤占普通数字编号

    # 专项导入后普通项目下一编号不受影响（仍为常规 max+1）
    reg = db_session.query(Project).filter(Project.is_special.is_(False)).one()
    assert reg.code == "1"


def test_14_special_numeric_code_legacy(client, db_session):
    """历史专项占用了普通号段内的数字编号时，普通取号逐项跳过、专项取号走 ZX。

    场景：常规 1/2 + 历史专项占 "3" → 下一普通 = 4（跳过 3），下一专项 = ZX001。
    """
    from app.services.project_code import next_project_code, next_special_code

    a = _mk_project(db_session, "常规A"); a.code = "1"
    b = _mk_project(db_session, "常规B"); b.code = "2"
    legacy = _mk_project(db_session, "历史专项", is_special=True); legacy.code = "3"
    db_session.commit()

    assert next_project_code(db_session) == "4"   # 跳过被专项占用的 3
    assert next_special_code(db_session) == "ZX001"

    zx = _mk_project(db_session, "新专项", is_special=True); zx.code = "ZX001"
    db_session.commit()
    assert next_special_code(db_session) == "ZX002"
    assert next_project_code(db_session) == "4"   # 新增专项不影响普通序列


def test_14_special_create_api_uses_zx(client, db_session):
    """POST /api/projects 带 is_special=true 时取 ZX 编号，普通创建仍走数字序列。"""

    resp = client.post("/api/projects", json={
        "category": "新需求", "name": "API专项", "owner": "张三",
        "market": "拉美区", "status": "未开始", "is_special": True,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["code"] == "ZX001"

    resp2 = client.post("/api/projects", json={
        "category": "新需求", "name": "API常规", "owner": "张三",
        "market": "拉美区", "status": "未开始",
    })
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["code"] == "1"  # 普通序列从 1 起，未被专项挤占


def test_14_special_import_permissions(client, db_session):
    """用例 14b：专项导入/预览仅 admin/manager——engineer/viewer 403；manager 200。"""
    data = _make_workbook([
        [1, "新需求", "权限专项导入", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
    ])

    # engineer / viewer → 403（预览 + 导入都要拦）
    _mk_user(db_session, "eng_simp", "engineer", "工程师丁")
    _mk_user(db_session, "view_simp", "viewer", "观察员丙")
    db_session.commit()
    _login(client, "eng_simp")
    assert client.post("/api/import/special-preview",
                       files={"file": ("t.xlsx", data)}).status_code == 403
    assert client.post("/api/import/special",
                       files={"file": ("t.xlsx", data)}).status_code == 403
    _login(client, "view_simp")
    assert client.post("/api/import/special-preview",
                       files={"file": ("t.xlsx", data)}).status_code == 403
    assert client.post("/api/import/special",
                       files={"file": ("t.xlsx", data)}).status_code == 403

    # manager → 200（预览 + 导入）
    _mk_user(db_session, "mgr_simp", "manager", "经理丙")
    db_session.commit()
    _login(client, "mgr_simp")
    resp = client.post("/api/import/special-preview", files={"file": ("t.xlsx", data)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["incoming"]["projects"] == 1
    resp = client.post("/api/import/special", files={"file": ("t.xlsx", data)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["projects_imported"] == 1
    assert db_session.query(Project).filter(Project.is_special.is_(True)).count() == 1


def test_14_parse_special_mode_raw_phase_type(db_session):
    """用例 14c（单元）：parse_workbook(special=True) 阶段类型列原样存储、无警告；
    旧格式无类型列 → phase_type 留空；对照：常规模式同样内容会警告+跳过。"""
    from app.services.excel_importer import parse_workbook

    # 新格式：任意自由文本阶段类型
    data = _make_workbook([
        [1, "新需求", "专项解析A", "张三", "拉美区", "", "2026-07-01", "2026-08-01", "", "", "", "", "", ""],
        ["1-1", "", "", "", "", "电磁兼容测试", "2026-07-01", "2026-07-20", "", "", "李四", "进行中", 30, ""],
    ])
    parsed = parse_workbook(data, special=True)
    assert len(parsed.projects) == 1
    assert parsed.projects[0].phases[0].phase_type == "电磁兼容测试"
    assert parsed.projects[0].phases[0].name == "电磁兼容测试"
    assert parsed.report.errors == [] and parsed.report.warnings == []

    # 对照：常规模式同一文件 → 任意类型不可解析，警告 + 跳过该行
    parsed_reg = parse_workbook(data)
    assert parsed_reg.projects[0].phases == []
    assert any("无法识别" in w.message for w in parsed_reg.report.warnings)

    # 旧格式：无阶段类型列 → phase_type 留空（不映射、不 error）；阶段名走名称列
    old = _make_old_workbook([
        [1, "新需求", "旧格式专项", "张三", "", "", "进行中", ""],
        ["1-1", "", "电磁兼容测试", "李四", "", "", "已完成", ""],
    ])
    parsed_old = parse_workbook(old, special=True)
    assert len(parsed_old.projects) == 1
    ph = parsed_old.projects[0].phases[0]
    assert ph.phase_type == "" and ph.name == "电磁兼容测试"
    assert ph.assignees == ["李四"]
    assert parsed_old.report.errors == []
