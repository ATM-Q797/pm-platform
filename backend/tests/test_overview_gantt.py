"""进行中项目总览甘特 /api/projects/overview-gantt（项目总览甘特批 2026-11-19）。

口径与验收：
- 仅进行中项目（status == '进行中'），未开始/已完成/搁置排除
- 角色可见范围与项目列表共用 _visible_projects_stmt（admin/viewer 全部、
  manager 创建+参与、engineer 参与、无 resource 的 engineer 空集）
- 专项项目排除
- 排序同项目列表：plan_start 升序、无日期最后、同日期按 id
- 数据结构：项目行负 id（-project_id）+ 阶段子行 parent 指回 + 依赖连线一并下发
- 未登录 401
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.security import hash_password
from app.models import Dependency, Phase, Project, Resource, User


def _mk_project(db, name: str, *, status: str = "进行中",
                plan_start: date | None = date(2026, 11, 1),
                plan_end: date | None = date(2026, 12, 1),
                is_special: bool = False, created_by: int | None = None) -> Project:
    p = Project(code=f"OV-{name}", category="新需求", name=name, owner="负责人甲",
                market="拉美区", status=status, plan_start=plan_start, plan_end=plan_end,
                is_special=is_special, created_by=created_by)
    db.add(p)
    db.flush()
    return p


def _mk_phase(db, project: Project, name: str, sequence: int = 1, *,
              start: date | None = date(2026, 11, 1), end: date | None = date(2026, 11, 10),
              status: str = "进行中", progress: int = 50,
              assignees: list[Resource] | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P1", name=name, sequence=sequence,
               plan_start=start, plan_end=end, status=status, progress=progress)
    if assignees:
        ph.assignees = assignees
    db.add(ph)
    db.flush()
    return ph


def _mk_user(db, username: str, role: str, *, resource_id: int | None = None) -> User:
    u = User(username=username, name=f"用户{username}", role=role,
             password_hash=hash_password("testpass"), must_change_password=False,
             resource_id=resource_id)
    db.add(u)
    db.flush()
    return u


def _login(client, username: str, password: str = "testpass") -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


# ---------- 口径过滤 ----------

@pytest.mark.usefixtures("client")
class TestOverviewGanttFiltering:

    def test_401_without_login(self, client, db_session):
        client.post("/api/auth/logout")
        assert client.get("/api/projects/overview-gantt").status_code == 401

    def test_only_in_progress_projects(self, client, db_session):
        """仅进行中：未开始/已完成/搁置排除（admin 视角）。"""
        p_active = _mk_project(db_session, "进行中项目")
        _mk_phase(db_session, p_active, "阶段一")
        _mk_project(db_session, "未开始项目", status="未开始")
        _mk_project(db_session, "已完成项目", status="已完成")
        _mk_project(db_session, "搁置项目", status="搁置")
        db_session.commit()

        rows = client.get("/api/projects/overview-gantt").json()["data"]
        proj_names = [t["text"] for t in rows if t["type"] == "project"]
        assert proj_names == ["进行中项目"]

    def test_special_projects_excluded(self, client, db_session):
        """专项项目排除（SPECIAL_PROJECT §4.3 同列表口径）。"""
        _mk_project(db_session, "普通进行中")
        _mk_project(db_session, "专项进行中", is_special=True)
        db_session.commit()

        rows = client.get("/api/projects/overview-gantt").json()["data"]
        assert all(t["text"] != "专项进行中" for t in rows)

    def test_empty_when_no_active(self, client, db_session):
        """无进行中项目 → data 空数组（前端显示空态）。"""
        _mk_project(db_session, "已完成项目", status="已完成")
        db_session.commit()
        assert client.get("/api/projects/overview-gantt").json()["data"] == []


# ---------- 数据结构 ----------

@pytest.mark.usefixtures("client")
class TestOverviewGanttStructure:

    def test_row_ids_and_fields(self, client, db_session):
        """项目行负 id + 阶段子行 parent 指回 + 扩展字段下发。"""
        from app.models import phase_assignee  # noqa: F401  确认关联表已注册
        res = Resource(name="总览甘特员")
        db_session.add(res)
        db_session.flush()
        p = _mk_project(db_session, "结构项目", plan_start=date(2026, 11, 1), plan_end=date(2026, 12, 15))
        ph1 = _mk_phase(db_session, p, "阶段甲", 1, progress=20, assignees=[res])
        ph2 = _mk_phase(db_session, p, "阶段乙", 2, start=date(2026, 11, 11),
                        end=date(2026, 12, 10), status="未开始", progress=0)
        db_session.add(Dependency(from_phase_id=ph1.id, to_phase_id=ph2.id, type="FS", lag_days=0))
        db_session.commit()

        body = client.get("/api/projects/overview-gantt").json()
        rows, links = body["data"], body["links"]

        proj = next(t for t in rows if t["type"] == "project")
        assert proj["id"] == -p.id
        assert proj["parent"] == 0
        assert proj["owner_name"] == "负责人甲"
        assert proj["project_id"] == p.id
        assert proj["open"] is False  # 默认收起
        assert proj["start_date"] == "2026-11-01"
        # 平均进度 (20+0)/2 = 10 → 0.1
        assert proj["progress"] == pytest.approx(0.1)

        phase_rows = [t for t in rows if t["type"] == "task"]
        assert [t["text"] for t in phase_rows] == ["阶段甲", "阶段乙"]
        for t in phase_rows:
            assert t["parent"] == -p.id
            assert t["project_id"] == p.id
            assert t["status"] in ("进行中", "未开始")
        by_name = {t["text"]: t for t in phase_rows}
        assert by_name["阶段甲"]["assignee_names"] == "总览甘特员"
        assert by_name["阶段甲"]["progress"] == pytest.approx(0.2)
        assert by_name["阶段乙"]["assignee_names"] is None

        # 依赖连线跨下发（展开项目行后显示箭头）
        assert len(links) == 1
        assert links[0]["source"] == ph1.id
        assert links[0]["target"] == ph2.id

    def test_order_same_as_project_list(self, client, db_session):
        """排序同列表：plan_start 升序、无日期最后。"""
        _mk_project(db_session, "B-中", plan_start=date(2026, 6, 1))
        _mk_project(db_session, "C-晚", plan_start=date(2026, 9, 1))
        _mk_project(db_session, "D-无日期", plan_start=None)
        _mk_project(db_session, "A-早", plan_start=date(2026, 3, 1))
        db_session.commit()

        rows = client.get("/api/projects/overview-gantt").json()["data"]
        assert [t["text"] for t in rows if t["type"] == "project"] == \
            ["A-早", "B-中", "C-晚", "D-无日期"]


# ---------- 角色可见范围（与项目列表同一口径） ----------

@pytest.mark.usefixtures("client")
class TestOverviewGanttVisibility:

    def test_engineer_sees_only_joined(self, client, db_session):
        """engineer 仅看自己参与的（resource 被分配到该项目的阶段）。"""
        res = Resource(name="总览工程师资源")
        db_session.add(res)
        db_session.flush()
        p_joined = _mk_project(db_session, "参与项目")
        _mk_phase(db_session, p_joined, "参与阶段", assignees=[res])
        p_other = _mk_project(db_session, "无关项目")
        _mk_phase(db_session, p_other, "无关阶段")
        _mk_user(db_session, "ov_eng", "engineer", resource_id=res.id)
        db_session.commit()

        _login(client, "ov_eng")
        rows = client.get("/api/projects/overview-gantt").json()["data"]
        assert [t["text"] for t in rows if t["type"] == "project"] == ["参与项目"]

    def test_engineer_without_resource_empty(self, client, db_session):
        """engineer 未关联 resource → 空集（list_projects 同款兜底语义）。"""
        _mk_project(db_session, "进行中项目")
        _mk_user(db_session, "ov_eng2", "engineer")
        db_session.commit()

        _login(client, "ov_eng2")
        assert client.get("/api/projects/overview-gantt").json()["data"] == []

    def test_manager_created_or_joined(self, client, db_session):
        """manager：自己创建的 + 自己参与的都可见；无关项目不可见。"""
        res = Resource(name="总览经理资源")
        db_session.add(res)
        db_session.flush()
        mgr = _mk_user(db_session, "ov_mgr", "manager", resource_id=res.id)

        p_created = _mk_project(db_session, "经理自建", created_by=mgr.id)
        _mk_phase(db_session, p_created, "自建阶段")
        p_joined = _mk_project(db_session, "经理参与")
        _mk_phase(db_session, p_joined, "参与阶段", assignees=[res])
        p_other = _mk_project(db_session, "无关项目")
        _mk_phase(db_session, p_other, "无关阶段")
        db_session.commit()

        _login(client, "ov_mgr")
        rows = client.get("/api/projects/overview-gantt").json()["data"]
        assert sorted(t["text"] for t in rows if t["type"] == "project") == \
            ["经理参与", "经理自建"]


# ---------- 与项目列表一致性 ----------

def test_overview_matches_list_order_and_scope(client, db_session):
    """总览项目集与 /api/projects?status=进行中 完全一致（同范围函数 + 同排序）。"""
    _mk_project(db_session, "一致性甲", plan_start=date(2026, 5, 1))
    _mk_project(db_session, "一致性乙", plan_start=None)
    _mk_project(db_session, "一致性丙", plan_start=date(2026, 7, 1), status="已完成")
    _mk_project(db_session, "一致性专项", is_special=True)
    db_session.commit()

    list_rows = client.get("/api/projects", params={"status": "进行中"}).json()
    overview_rows = client.get("/api/projects/overview-gantt").json()["data"]
    assert [p["name"] for p in list_rows] == \
        [t["text"] for t in overview_rows if t["type"] == "project"] == \
        ["一致性甲", "一致性乙"]
