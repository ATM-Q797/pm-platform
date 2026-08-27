"""项目「搁置」状态测试（PROJECT_SHELVE v1.1）。

覆盖：
- §2.1 项目更新接口：'搁置' 保存成功；旧值 '已搁置' 归一化为 '搁置'；其他非法值 422
- §2.2 看板：搁置项目（新值+旧值）的阶段不进入 delayed_phases / due_soon_phases
- §2.3 冲突：搁置项目的阶段不产生冲突对；阶段级「已搁置」仍跳过（回归）
- §2.4 迁移：migrate_v3.sql 可执行，'已搁置' → '搁置'（幂等）
- 前端双 key 契约：状态常量表同时含 '搁置' 与 '已搁置'（对源码做静态断言，tsc/build 兜底）
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEPLOY_DIR = BACKEND_DIR.parent / "deploy"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend" / "src"

from app.models import Phase, Project, Resource  # noqa: E402


def _today() -> date:
    return date.today()


def _mk_project(db_session, name: str, status: str = "进行中") -> Project:
    p = Project(code=str(len(list(db_session.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区", status=status)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, start: date, end: date,
              status: str = "进行中") -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50)
    db_session.add(ph)
    db_session.flush()
    return ph


# ---------- §2.1 项目更新接口：状态校验与归一化 ----------

def test_update_status_shelve_saved(client, db_session):
    """传 '搁置' 直接保存成功。"""
    p = _mk_project(db_session, "搁置项目A")
    db_session.commit()

    resp = client.put(f"/api/projects/{p.id}", json={"status": "搁置"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "搁置"
    assert db_session.get(Project, p.id).status == "搁置"


def test_update_status_legacy_normalized(client, db_session):
    """旧值 '已搁置' 归一化为 '搁置' 保存（PROJECT_SHELVE 决策 1）。"""
    p = _mk_project(db_session, "搁置项目B")
    db_session.commit()

    resp = client.put(f"/api/projects/{p.id}", json={"status": "已搁置"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "搁置"
    assert db_session.get(Project, p.id).status == "搁置"


def test_update_status_invalid_422(client, db_session):
    """其他非法状态值 → 422，且库中状态不变。"""
    p = _mk_project(db_session, "正常项目")
    db_session.commit()

    resp = client.put(f"/api/projects/{p.id}", json={"status": "其他"})
    assert resp.status_code == 422
    assert db_session.get(Project, p.id).status == "进行中"


def test_update_status_untouched_when_absent(client, db_session):
    """部分更新（不传 status）不影响现有状态。"""
    p = _mk_project(db_session, "部分更新项目")
    db_session.commit()

    resp = client.put(f"/api/projects/{p.id}", json={"remark": "只改备注"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "进行中"


# ---------- §2.2 看板排除（搁置项目不报警） ----------

def test_dashboard_delayed_excludes_shelved_project(client, db_session):
    """搁置项目（新值+旧值）的逾期阶段不进入 delayed_phases；正常项目保留。"""
    t = _today()
    p_new = _mk_project(db_session, "搁置项目（新值）", status="搁置")
    p_old = _mk_project(db_session, "搁置项目（旧值）", status="已搁置")
    p_ok = _mk_project(db_session, "活跃项目", status="进行中")
    _mk_phase(db_session, p_new, "搁置新值逾期阶段", t - timedelta(days=10), t - timedelta(days=3))
    _mk_phase(db_session, p_old, "搁置旧值逾期阶段", t - timedelta(days=10), t - timedelta(days=3))
    ok = _mk_phase(db_session, p_ok, "活跃逾期阶段", t - timedelta(days=10), t - timedelta(days=3))
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    names = [d["phase_name"] for d in data["delayed_phases"]]
    assert names == ["活跃逾期阶段"]
    assert names and data["delayed_phases"][0]["phase_id"] == ok.id


def test_dashboard_due_soon_excludes_shelved_project(client, db_session):
    """搁置项目（新值+旧值）的即将到期阶段不进入 due_soon_phases。"""
    t = _today()
    p_new = _mk_project(db_session, "搁置项目（新值）", status="搁置")
    p_old = _mk_project(db_session, "搁置项目（旧值）", status="已搁置")
    p_ok = _mk_project(db_session, "活跃项目", status="进行中")
    _mk_phase(db_session, p_new, "搁置新值到期阶段", t, t + timedelta(days=3))
    _mk_phase(db_session, p_old, "搁置旧值到期阶段", t, t + timedelta(days=3))
    _mk_phase(db_session, p_ok, "活跃到期阶段", t, t + timedelta(days=3))
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    names = [d["phase_name"] for d in data["due_soon_phases"]]
    assert names == ["活跃到期阶段"]
    assert data["due_soon_count"] == 1


def test_dashboard_project_level_delay_unchanged(client, db_session):
    """回归：项目级延期用 _ACTIVE_STATUSES（未开始/进行中），搁置项目本来就不报。"""
    t = _today()
    p_new = _mk_project(db_session, "搁置项目（新值）", status="搁置")
    p_old = _mk_project(db_session, "搁置项目（旧值）", status="已搁置")
    p_ok = _mk_project(db_session, "活跃项目", status="进行中")
    for p in (p_new, p_old, p_ok):
        p.plan_end = t - timedelta(days=5)
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    delayed_names = [d["name"] for d in data["delayed_projects"]]
    assert delayed_names == ["活跃项目"]


# ---------- §2.3 资源冲突排除 ----------

def test_conflicts_exclude_shelved_project_phases(client, db_session):
    """搁置项目的阶段与其他阶段深度重叠也不产生冲突对（§2.3，双 key）。"""
    t = _today()
    r = Resource(name="冲突检测人")
    db_session.add(r)
    db_session.flush()
    p_shelved = _mk_project(db_session, "搁置冲突项目", status="搁置")
    p_other = _mk_project(db_session, "其他冲突项目", status="进行中")
    a = _mk_phase(db_session, p_shelved, "搁置项目阶段", t, t + timedelta(days=30))
    b = _mk_phase(db_session, p_other, "其他项目阶段", t, t + timedelta(days=30))
    a.assignees = [r]
    b.assignees = [r]
    # 并行数推到 4：若无搁置排除，这对 30 天整段重叠必然报冲突
    for i in range(2):
        p_extra = _mk_project(db_session, f"并行项目{i + 1}", status="进行中")
        ph = _mk_phase(db_session, p_extra, f"并行阶段{i + 1}", t, t + timedelta(days=30))
        ph.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    # 搁置项目阶段退出检测：剩 3 个活跃阶段（≤ _MAX_PARALLEL）→ 无冲突
    assert data == []

    # 新值 '搁置' 已验证；旧值 '已搁置' 同样排除（同一过滤口径）
    p_shelved.status = "已搁置"
    db_session.commit()
    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_conflicts_active_project_still_reported(client, db_session):
    """回归：非搁置项目的深度重叠照常报冲突（排除逻辑不误伤）。"""
    t = _today()
    r = Resource(name="正常冲突人")
    db_session.add(r)
    db_session.flush()
    p1 = _mk_project(db_session, "冲突项目一", status="进行中")
    p2 = _mk_project(db_session, "冲突项目二", status="进行中")
    a = _mk_phase(db_session, p1, "阶段一", t, t + timedelta(days=30))
    b = _mk_phase(db_session, p2, "阶段二", t, t + timedelta(days=30))
    a.assignees = [r]
    b.assignees = [r]
    for i in range(2):
        p_extra = _mk_project(db_session, f"并行补充项目{i + 1}", status="进行中")
        ph = _mk_phase(db_session, p_extra, f"并行补充阶段{i + 1}", t, t + timedelta(days=30))
        ph.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert len(data) == 1
    assert len(data[0]["conflicts"]) == 6  # 4 个活跃阶段两两组合


def test_conflicts_phase_level_shelved_still_skipped(client, db_session):
    """回归：阶段级「已搁置」仍跳过（_SKIP_STATUSES 不变，PROJECT_SHELVE §2.3）。"""
    t = _today()
    r = Resource(name="阶段搁置人")
    db_session.add(r)
    db_session.flush()
    p1 = _mk_project(db_session, "阶段搁置项目一", status="进行中")
    p2 = _mk_project(db_session, "阶段搁置项目二", status="进行中")
    a = _mk_phase(db_session, p1, "已完成阶段", t, t + timedelta(days=30), status="已完成")
    b = _mk_phase(db_session, p2, "已搁置阶段", t, t + timedelta(days=30), status="已搁置")
    a.assignees = [r]
    b.assignees = [r]
    for i in range(2):
        p_extra = _mk_project(db_session, f"阶段搁置并行{i + 1}", status="进行中")
        ph = _mk_phase(db_session, p_extra, f"阶段搁置并行阶段{i + 1}", t, t + timedelta(days=30))
        ph.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    # 已完成/已搁置（阶段级）退出检测：剩 2 个活跃阶段 → 无冲突
    assert data == []


# ---------- §2.4 迁移脚本 ----------

def test_migrate_v3_sql_executable(tmp_path):
    """migrate_v3.sql 在 SQLite 上可执行：'已搁置' → '搁置'，幂等。"""
    sql_path = DEPLOY_DIR / "migrate_v3.sql"
    assert sql_path.exists(), "deploy/migrate_v3.sql 缺失"

    conn = sqlite3.connect(tmp_path / "migrate_test.db")
    try:
        conn.execute(
            "CREATE TABLE project (id INTEGER PRIMARY KEY, status TEXT NOT NULL)"
        )
        for s in ("未开始", "进行中", "已完成", "搁置", "已搁置", "已搁置"):
            conn.execute("INSERT INTO project (status) VALUES (?)", (s,))
        conn.commit()

        # executescript 可执行带注释的多语句脚本
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        statuses = [row[0] for row in conn.execute("SELECT status FROM project ORDER BY id")]
        assert statuses == ["未开始", "进行中", "已完成", "搁置", "搁置", "搁置"]

        # 幂等：重复执行无副作用
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        assert [row[0] for row in conn.execute("SELECT status FROM project ORDER BY id")] == statuses
    finally:
        conn.close()


# ---------- 前端双 key 契约（静态断言，tsc/build 由验收命令兜底） ----------

def test_frontend_status_color_dual_keys():
    """列表/详情页 STATUS_COLOR 同时含 '搁置' 与 '已搁置'（迁移前旧数据不显示无色 Tag）。"""
    for page in ("pages/ProjectListPage.tsx", "pages/ProjectDetailPage.tsx"):
        text = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        m = re.search(r"const STATUS_COLOR[^=]*=\s*\{([^}]+)\}", text)
        assert m, f"{page} 缺少 STATUS_COLOR 定义"
        body = m.group(1)
        assert re.search(r"^\s*搁置:\s*'", body, re.M), f"{page} STATUS_COLOR 缺少 '搁置' key"
        assert re.search(r"^\s*已搁置:\s*'", body, re.M), f"{page} STATUS_COLOR 缺少 '已搁置' key"


def test_frontend_filter_and_edit_options_dual_keys():
    """列表页筛选条与编辑弹窗 options 双 key：主选项 '搁置'，兼容选项 '已搁置'。"""
    text = (FRONTEND_DIR / "pages" / "ProjectListPage.tsx").read_text(encoding="utf-8")
    # 筛选条 + 编辑弹窗各出现一次「搁置」主选项与「已搁置」兼容选项
    assert text.count("{ value: '搁置', label: '搁置' }") == 2
    assert text.count("value: '已搁置'") == 2
