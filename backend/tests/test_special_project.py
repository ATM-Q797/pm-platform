"""专项项目页面测试（SPECIAL_PROJECT §七）。

覆盖：三处资源负载排除（热力/甘特/冲突）、自定义阶段类型、专项列表权限与路由顺序、
gantt remark、预警口径数据、开关切换与列表过滤、普通列表/Dashboard 隔离、
详情/阶段/项目级接口权限、列表聚合排除、角标边界（后端可测部分）。
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from io import BytesIO

import openpyxl

from app.core.security import hash_password
from app.models import Phase, Project, Resource, User

# ---- 公共构造 ----


def _mk_project(db_session, name: str, status: str = "进行中", is_special: bool = False,
                plan_end: date | None = None) -> Project:
    p = Project(code=f"{name}-{len(list(db_session.query(Project))) + 1}", category="新需求",
                name=name, owner="张三", market="拉美区", status=status,
                is_special=is_special, plan_end=plan_end)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, start: date | None, end: date | None,
              status: str = "进行中", phase_type: str = "P4", remark: str | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type=phase_type, name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50, remark=remark)
    db_session.add(ph)
    db_session.flush()
    return ph


def _mk_resource(db_session, name: str) -> Resource:
    r = Resource(name=name)
    db_session.add(r)
    db_session.flush()
    return r


def _mk_user(db_session, username: str, role: str, name: str = "测试用户") -> User:
    u = User(username=username, name=name, role=role,
             password_hash=hash_password("testpass"))
    db_session.add(u)
    return u


def _login(client, username: str):
    resp = client.post("/api/auth/login", json={"username": username, "password": "testpass"})
    assert resp.status_code == 200, resp.text


def _today() -> date:
    return date.today()


def _week_monday(d: date) -> date:
    """d 所在周的周一（与后端热力桶对齐规则一致）。"""
    return d - timedelta(days=d.weekday())


# ---- §七 用例 ----


def test_1_special_phase_excluded_from_all_resource_views(client, db_session):
    """用例 1：专项项目阶段 → 热力图不占格、资源甘特不显示、冲突不报（三处排除）。"""
    t = _today()
    r = _mk_resource(db_session, "专项排除人")
    # 4 个普通项目阶段同窗深度重叠（并行 4 > 3 → 若无排除报 C(5,2)=10 对）
    for i in range(4):
        p = _mk_project(db_session, f"普通项目{i + 1}")
        _mk_phase(db_session, p, f"普通阶段{i + 1}", t, t + timedelta(days=30)).assignees = [r]
    # 专项项目阶段同一窗口
    sp = _mk_project(db_session, "专项项目", is_special=True)
    _mk_phase(db_session, sp, "专项阶段", t, t + timedelta(days=30)).assignees = [r]
    db_session.commit()

    # 冲突：仅 4 个普通阶段参与 → C(4,2)=6 对，专项阶段不在任何对里
    conflicts = client.get("/api/resources/conflicts").json()
    assert len(conflicts) == 1
    pairs = conflicts[0]["conflicts"]
    assert len(pairs) == 6
    involved = {c["phase_a_id"] for c in pairs} | {c["phase_b_id"] for c in pairs}
    assert all(ph.id not in involved for ph in db_session.query(Phase).filter(Phase.name == "专项阶段"))

    # 热力图：当前周桶格值 = 4（不含专项），peak=4（30 天阶段跨 ~5 周，sum 断言按桶）
    hm = client.get("/api/resources/heatmap").json()
    row = next(p for p in hm["people"] if p["resource_id"] == r.id)
    cur_col = hm["columns"].index(_week_monday(t).isoformat())
    assert row["cells"][cur_col] == 4 and row["peak_parallel"] == 4
    phase_ids = {e["phase_id"] for cp in row["cell_phases"] if cp for e in cp}
    assert all(ph.id not in phase_ids for ph in db_session.query(Phase).filter(Phase.name == "专项阶段"))

    # 资源甘特：/all/workload 与 /{id}/workload 均不含专项阶段
    all_wl = client.get("/api/resources/all/workload").json()
    me = next(w for w in all_wl if w["resource"]["id"] == r.id)
    assert len(me["workloads"]) == 4
    assert all("专项" not in w["project_name"] for w in me["workloads"])


def test_2_custom_phase_type_saved_and_gantt_ok(client, db_session):
    """用例 2：专项项目阶段类型自由文本（如"电磁兼容测试"）→ 保存成功、甘特正常。"""
    resp = client.post("/api/projects", json={
        "name": "专项自由类型", "category": "定制", "owner": "张三", "market": "拉美区",
        "is_special": True,
    })
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    t = _today()
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "电磁兼容测试", "name": "电磁兼容测试", "sequence": 1,
        "plan_start": t.isoformat(), "plan_end": (t + timedelta(days=10)).isoformat(),
        "status": "进行中", "progress": 30,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["phase_type"] == "电磁兼容测试"

    gantt = client.get(f"/api/projects/{pid}/gantt")
    assert gantt.status_code == 200, gantt.text
    task_texts = [tk["text"] for tk in gantt.json()["data"]]
    assert "电磁兼容测试" in task_texts


def test_4_special_list_permissions_and_route_order(client, db_session):
    """用例 4：专项列表 admin/manager 200；engineer/viewer 403；/special 不被 /{project_id} 吞掉。"""
    _mk_project(db_session, "专项路由项目", is_special=True)
    db_session.commit()

    # admin（默认登录）200 且返回专项
    resp = client.get("/api/projects/special")
    assert resp.status_code == 200, resp.text
    assert [p["name"] for p in resp.json()] == ["专项路由项目"]

    # manager 200
    _mk_user(db_session, "mgr_special", "manager", "经理甲")
    db_session.commit()
    _login(client, "mgr_special")
    resp = client.get("/api/projects/special")
    assert resp.status_code == 200, resp.text

    # engineer 403（路由未被 /{project_id} 吞掉：若被吞会 422，而非 403）
    _mk_user(db_session, "eng_special", "engineer", "工程师甲")
    db_session.commit()
    _login(client, "eng_special")
    resp = client.get("/api/projects/special")
    assert resp.status_code == 403, resp.text

    # viewer 403
    _mk_user(db_session, "view_special", "viewer", "观察员甲")
    db_session.commit()
    _login(client, "view_special")
    resp = client.get("/api/projects/special")
    assert resp.status_code == 403, resp.text


def test_5_gantt_remark_carried(client, db_session):
    """用例 5：gantt 响应 remark：阶段有备注 → task.remark 携带（项目甘特 + /all/workload）。"""
    t = _today()
    r = _mk_resource(db_session, "备注人")
    p = _mk_project(db_session, "备注项目")
    ph = _mk_phase(db_session, p, "备注阶段", t, t + timedelta(days=7), remark="注意：样机需提前")
    ph.assignees = [r]
    db_session.commit()

    gantt = client.get(f"/api/projects/{p.id}/gantt")
    assert gantt.status_code == 200
    task = next(tk for tk in gantt.json()["data"] if tk["id"] == ph.id)
    assert task["remark"] == "注意：样机需提前"

    all_wl = client.get("/api/resources/all/workload").json()
    me = next(w for w in all_wl if w["resource"]["id"] == r.id)
    item = next(w for w in me["workloads"] if w["phase_id"] == ph.id)
    assert item["remark"] == "注意：样机需提前"


def test_6_badge_input_data_available(client, db_session):
    """用例 6：预警口径相关字段（延期/即将到期/无阶段）在 /special 响应中可用且正确。"""
    t = _today()
    _mk_project(db_session, "专项延期", status="进行中", is_special=True, plan_end=t - timedelta(days=5))
    _mk_project(db_session, "专项到期", status="进行中", is_special=True, plan_end=t + timedelta(days=3))
    _mk_project(db_session, "专项无阶段", status="进行中", is_special=True, plan_end=t + timedelta(days=30))
    db_session.commit()

    resp = client.get("/api/projects/special")
    assert resp.status_code == 200
    by_name = {p["name"]: p for p in resp.json()}

    # 延期：plan_end < today 且未完成（前端 🔴 触发条件的数据就绪）
    assert by_name["专项延期"]["plan_end"] == (t - timedelta(days=5)).isoformat()
    assert by_name["专项延期"]["status"] == "进行中"
    # 即将到期：plan_end 在 7 天内（前端 🟡 触发条件的数据就绪）
    assert by_name["专项到期"]["plan_end"] == (t + timedelta(days=3)).isoformat()
    # 无阶段：phases 为空（前端 ⚠️ 触发条件的数据就绪）
    assert by_name["专项无阶段"]["phases"] == []


def test_7_is_special_toggle_effective(client, db_session):
    """用例 7：创建/更新 is_special 开关生效、列表正确过滤。"""
    # 创建 is_special=true
    resp = client.post("/api/projects", json={
        "name": "开关项目", "category": "新需求", "owner": "张三", "market": "拉美区",
        "is_special": True,
    })
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    assert resp.json()["is_special"] is True

    # 专项列表有、普通列表无
    assert [p["id"] for p in client.get("/api/projects/special").json()] == [pid]
    assert all(p["id"] != pid for p in client.get("/api/projects").json())

    # 更新取消开关 → 进普通列表、出专项列表
    resp = client.put(f"/api/projects/{pid}", json={"is_special": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_special"] is False
    assert all(p["id"] != pid for p in client.get("/api/projects/special").json())
    assert any(p["id"] == pid for p in client.get("/api/projects").json())

    # 普通项目更新为 is_special=true → 反向迁移
    resp = client.put(f"/api/projects/{pid}", json={"is_special": True})
    assert resp.status_code == 200
    assert [p["id"] for p in client.get("/api/projects/special").json()] == [pid]
    assert all(p["id"] != pid for p in client.get("/api/projects").json())


def test_8_normal_list_and_dashboard_isolated(client, db_session):
    """用例 8：普通列表与 Dashboard 隔离（is_special=true 不出现在普通列表与 Dashboard 统计）。"""
    t = _today()
    # 普通：延期项目 + 进行中阶段（有返工）
    p_norm = _mk_project(db_session, "普通统计项目", status="进行中", plan_end=t - timedelta(days=2))
    ph_norm = _mk_phase(db_session, p_norm, "普通延期阶段", t - timedelta(days=10), t - timedelta(days=1))
    ph_norm.rework_count = 2
    # 专项：同样延期 + 阶段有返工
    sp = _mk_project(db_session, "专项统计项目", status="进行中", is_special=True, plan_end=t - timedelta(days=2))
    ph_sp = _mk_phase(db_session, sp, "专项延期阶段", t - timedelta(days=10), t - timedelta(days=1))
    ph_sp.rework_count = 3
    db_session.commit()

    # 普通列表
    names = [p["name"] for p in client.get("/api/projects").json()]
    assert "普通统计项目" in names and "专项统计项目" not in names

    # Dashboard 统计
    stats = client.get("/api/dashboard/stats").json()
    assert stats["total_projects"] == 1
    assert [d["name"] for d in stats["delayed_projects"]] == ["普通统计项目"]
    assert {s["status"] for s in stats["project_status"]} == {"进行中"}
    assert stats["total_rework_count"] == 2
    assert [r["project_name"] for r in stats["rework_phases"]] == ["普通统计项目"]
    assert [d["project_name"] for d in stats["delayed_phases"]] == ["普通统计项目"]


def test_9_detail_phase_permissions(client, db_session):
    """用例 9：非 admin/manager 访问专项详情/甘特/阶段 → 403；普通项目不受影响。

    engineer 已关联 resource 并分配到专项/普通阶段——若没有专项守卫，check_phase_access
    会放行工程师改被分配的阶段（200）；守卫存在时专项阶段一律 403，普通阶段维持 200。
    """
    t = _today()
    sp = _mk_project(db_session, "权限专项", is_special=True)
    sp_ph = _mk_phase(db_session, sp, "专项权限阶段", t, t + timedelta(days=5))
    np = _mk_project(db_session, "权限普通")
    np_ph = _mk_phase(db_session, np, "普通权限阶段", t, t + timedelta(days=5))
    r_perm = _mk_resource(db_session, "权限人")
    sp_ph.assignees = [r_perm]
    np_ph.assignees = [r_perm]
    _mk_user(db_session, "eng_perm", "engineer", "工程师乙")
    db_session.commit()
    db_session.query(User).filter_by(username="eng_perm").first().resource_id = r_perm.id
    db_session.commit()

    _login(client, "eng_perm")

    # 专项：详情/甘特/阶段列表/阶段详情/阶段 CRUD 全 403
    assert client.get(f"/api/projects/{sp.id}").status_code == 403
    assert client.get(f"/api/projects/{sp.id}/gantt").status_code == 403
    assert client.get(f"/api/projects/{sp.id}/critical-path").status_code == 403
    assert client.get(f"/api/projects/{sp.id}/phases").status_code == 403
    assert client.get(f"/api/phases/{sp_ph.id}").status_code == 403
    assert client.put(f"/api/phases/{sp_ph.id}", json={"status": "已完成"}).status_code == 403
    assert client.post(f"/api/phases/{sp_ph.id}/move", params={"direction": "up"}).status_code == 403
    assert client.delete(f"/api/phases/{sp_ph.id}").status_code == 403
    assert client.post(f"/api/phases/{sp_ph.id}/rework",
                       json={"to_status": "未开始", "reason": "测试"}).status_code == 403
    assert client.post(f"/api/projects/{sp.id}/phases", json={
        "phase_type": "P5", "name": "新阶段", "sequence": 2,
    }).status_code == 403

    # 普通项目不受影响：详情/甘特/阶段列表 200；被分配工程师改普通阶段 200
    assert client.get(f"/api/projects/{np.id}").status_code == 200
    assert client.get(f"/api/projects/{np.id}/gantt").status_code == 200
    assert client.get(f"/api/projects/{np.id}/phases").status_code == 200
    resp = client.put(f"/api/phases/{np_ph.id}", json={"progress": 60})
    assert resp.status_code == 200, resp.text

    # viewer 同样 403
    _mk_user(db_session, "view_perm", "viewer", "观察员乙")
    db_session.commit()
    _login(client, "view_perm")
    assert client.get(f"/api/projects/{sp.id}").status_code == 403
    assert client.get(f"/api/projects/{sp.id}/gantt").status_code == 403
    assert client.get(f"/api/projects/{np.id}").status_code == 200


def test_10_list_aggregations_excluded(client, db_session):
    """用例 10：列表聚合排除：搜索/看板（GET /api/projects）无专项；独立聚合接口（Excel 导出）核对。"""
    _mk_project(db_session, "聚合专项", is_special=True)
    _mk_project(db_session, "聚合普通")
    db_session.commit()

    # 看板/搜索走 GET /api/projects：无专项（带筛选也一致）
    all_names = [p["name"] for p in client.get("/api/projects").json()]
    assert "聚合专项" not in all_names and "聚合普通" in all_names
    filtered = [p["name"] for p in client.get("/api/projects", params={"category": "新需求"}).json()]
    assert "聚合专项" not in filtered

    # 独立聚合接口：Excel 导出不含专项项目
    resp = client.get("/api/export/excel")
    assert resp.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    ws = wb.active
    exported = " ".join(str(row[2].value) for row in ws.iter_rows(min_row=3) if len(row) > 2 and row[2].value)
    assert "聚合普通" in exported
    assert "聚合专项" not in exported


def test_11_project_level_permissions(client, db_session):
    """用例 11：非 admin/manager 更新/删除专项项目、创建 is_special=true → 403。"""
    sp = _mk_project(db_session, "写权限专项", is_special=True)
    db_session.commit()

    _mk_user(db_session, "eng_write", "engineer", "工程师丙")
    _mk_user(db_session, "mgr_write", "manager", "经理乙")
    db_session.commit()

    # engineer：更新/删除专项项目 403；创建 is_special=true 403（创建本就需要 admin/manager）
    _login(client, "eng_write")
    assert client.put(f"/api/projects/{sp.id}", json={"name": "改名"}).status_code == 403
    assert client.delete(f"/api/projects/{sp.id}").status_code == 403
    assert client.post("/api/projects", json={
        "name": "工程师建专项", "category": "新需求", "owner": "张三", "market": "拉美区",
        "is_special": True,
    }).status_code == 403

    # manager：更新专项项目 200（专项项目不限于本人负责）；删除仍走申请流程 403
    _login(client, "mgr_write")
    resp = client.put(f"/api/projects/{sp.id}", json={"name": "经理改专项名"})
    assert resp.status_code == 200, resp.text
    assert client.delete(f"/api/projects/{sp.id}").status_code == 403
    # manager 创建 is_special=true → 201
    resp = client.post("/api/projects", json={
        "name": "经理建专项", "category": "新需求", "owner": "经理乙", "market": "拉美区",
        "is_special": True,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_special"] is True


def test_12_badge_boundaries_backend(client, db_session):
    """用例 12：角标边界（后端可测部分）：搁置/已完成专项无角标数据；plan_end 为空不触发延期/到期。"""
    t = _today()
    _mk_project(db_session, "搁置专项", status="搁置", is_special=True, plan_end=t - timedelta(days=10))
    _mk_project(db_session, "完成专项", status="已完成", is_special=True, plan_end=t - timedelta(days=3))
    _mk_project(db_session, "无期限专项", status="进行中", is_special=True, plan_end=None)
    db_session.commit()

    resp = client.get("/api/projects/special")
    assert resp.status_code == 200
    by_name = {p["name"]: p for p in resp.json()}

    # 搁置/已完成：数据上 plan_end 已过期但不触发角标（前端按 status 抑制）
    assert by_name["搁置专项"]["status"] == "搁置"
    assert by_name["完成专项"]["status"] == "已完成"
    # plan_end 为空：不触发延期/到期（字段为 null）
    assert by_name["无期限专项"]["plan_end"] is None
    assert by_name["无期限专项"]["status"] == "进行中"


def test_15_special_export_domain_and_permissions(client, db_session):
    """用例 15：专项导出——special=true 仅含专项项目、非 admin/manager 403；
    special=false 仅含常规项目（域隔离，用户 2026-08-28）。"""
    import openpyxl

    sp = _mk_project(db_session, "导出专项", is_special=True)
    _mk_project(db_session, "导出常规")
    db_session.commit()

    def _names(resp) -> list[str]:
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        names = []
        for r in range(3, ws.max_row + 1):
            v = ws.cell(row=r, column=3).value
            if v:
                names.append(v)
        return names

    # admin：专项导出只含专项
    resp = client.get("/api/export/excel", params={"special": True})
    assert resp.status_code == 200
    assert _names(resp) == ["导出专项"]
    # admin：常规导出只含常规
    resp2 = client.get("/api/export/excel")
    assert resp2.status_code == 200
    assert _names(resp2) == ["导出常规"]

    # engineer：专项导出 403；常规导出不受影响
    _mk_user(db_session, "eng_export", "engineer")
    db_session.commit()
    _login(client, "eng_export")
    resp3 = client.get("/api/export/excel", params={"special": True})
    assert resp3.status_code == 403
    resp4 = client.get("/api/export/excel")
    assert resp4.status_code == 200

    # viewer（观察者）：无导出权限，常规/专项一律 403（用户 2026-11-11 权限分级需求 2/3）
    _mk_user(db_session, "view_export", "viewer", "观察员丁")
    db_session.commit()
    _login(client, "view_export")
    resp5 = client.get("/api/export/excel")
    assert resp5.status_code == 403
    resp6 = client.get("/api/export/excel", params={"special": True})
    assert resp6.status_code == 403
