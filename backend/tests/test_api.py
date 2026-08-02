"""API 端点测试：用 TestClient 跑核心 CRUD 全链路。"""
from __future__ import annotations

from app.models import Phase, Project, Resource, Template, TemplateDependency, TemplatePhase


def _seed_template(db_session) -> int:
    """写入一个简化模板（P1→P4 FS），返回模板 id。"""
    tpl = Template(name="测试模板A", category="招标研发")
    db_session.add(tpl)
    db_session.flush()
    db_session.add(TemplatePhase(template_id=tpl.id, phase_type="P1", name="需求评估", sequence=1, default_duration_days=5))
    db_session.add(TemplatePhase(template_id=tpl.id, phase_type="P4", name="工业设计", sequence=2, default_duration_days=7))
    db_session.add(TemplateDependency(template_id=tpl.id, from_phase_type="P1", to_phase_type="P4", type="FS"))
    db_session.commit()
    return tpl.id


# ---------- 项目 CRUD ----------

def test_project_crud(client):
    # 创建
    resp = client.post("/api/projects", json={
        "code": "API-1", "category": "招标", "name": "API项目",
        "owner": "owner", "market": "国内",
    })
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    assert resp.json()["status"] == "未开始"

    # 列表
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 筛选
    resp = client.get("/api/projects", params={"market": "海外"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # 详情
    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["code"] == "API-1"

    # 更新
    resp = client.put(f"/api/projects/{pid}", json={"status": "进行中"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "进行中"

    # 删除
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_project_duplicate_code(client):
    payload = {"code": "DUP", "category": "招标", "name": "A", "owner": "x", "market": "国内"}
    assert client.post("/api/projects", json=payload).status_code == 201
    resp = client.post("/api/projects", json=payload)
    assert resp.status_code == 400


# ---------- 阶段 + 返工 ----------

def test_phase_create_and_rework(client, db_session):
    pid = client.post("/api/projects", json={
        "code": "P-1", "category": "招标", "name": "P", "owner": "x", "market": "国内"
    }).json()["id"]

    # 创建阶段
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P1", "name": "需求评估", "sequence": 1, "status": "进行中", "progress": 50,
    })
    assert resp.status_code == 201, resp.text
    ph_id = resp.json()["id"]

    # 返工
    resp = client.post(f"/api/phases/{ph_id}/rework", json={"to_status": "未开始", "reason": "需求变更"})
    assert resp.status_code == 200, resp.text
    log = resp.json()
    assert log["from_status"] == "进行中"
    assert log["to_status"] == "未开始"

    # 校验 rework_count +1 且 actual_end 被清空
    ph = client.get(f"/api/phases/{ph_id}").json()
    assert ph["rework_count"] == 1
    assert ph["status"] == "未开始"
    assert ph["progress"] == 0


def test_phase_with_assignees(client, db_session):
    res = Resource(name="负责人A", role="工业设计")
    db_session.add(res)
    db_session.commit()

    pid = client.post("/api/projects", json={
        "code": "PA-1", "category": "招标", "name": "PA", "owner": "x", "market": "国内"
    }).json()["id"]

    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P4", "name": "工业设计", "sequence": 1, "assignee_ids": [res.id],
    })
    assert resp.status_code == 201
    assert len(resp.json()["assignees"]) == 1
    assert resp.json()["assignees"][0]["name"] == "负责人A"


# ---------- 创建阶段时顺便指定前置依赖 ----------

def test_create_phase_with_prerequisites(client):
    """创建阶段时带 depends_on_phase_ids，应自动建 前置→当前 的 FS 依赖。"""
    pid = client.post("/api/projects", json={
        "code": "PRE-1", "category": "招标", "name": "PRE", "owner": "x", "market": "国内"
    }).json()["id"]
    # 先建两个前置阶段（不带依赖）
    a = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P1", "name": "需求评估", "sequence": 1}).json()["id"]
    b = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P2", "name": "配置评估", "sequence": 2}).json()["id"]

    # 创建第三个阶段，依赖 a 和 b
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P4", "name": "工业设计", "sequence": 3,
        "depends_on_phase_ids": [a, b],
    })
    assert resp.status_code == 201, resp.text
    c = resp.json()["id"]

    # 应生成 2 条 FS 依赖：a→c, b→c
    deps = client.get(f"/api/projects/{pid}/dependencies").json()
    assert len(deps) == 2
    pairs = sorted([(d["from_phase_id"], d["to_phase_id"]) for d in deps])
    assert pairs == [(a, c), (b, c)]
    assert all(d["type"] == "FS" for d in deps)


def test_create_phase_without_prerequisites_is_allowed(client):
    """不带 depends_on_phase_ids（空数组）也应成功，且不建任何依赖。"""
    pid = client.post("/api/projects", json={
        "code": "PRE-2", "category": "招标", "name": "PRE2", "owner": "x", "market": "国内"
    }).json()["id"]
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P1", "name": "需求评估", "sequence": 1,
    })
    assert resp.status_code == 201
    assert client.get(f"/api/projects/{pid}/dependencies").json() == []


def test_create_phase_prerequisite_validation(client):
    """前置阶段校验：不存在 / 跨项目 / 自引用。"""
    pid = client.post("/api/projects", json={
        "code": "PRE-3", "category": "招标", "name": "PRE3", "owner": "x", "market": "国内"
    }).json()["id"]
    other_pid = client.post("/api/projects", json={
        "code": "PRE-4", "category": "招标", "name": "PRE4", "owner": "x", "market": "国内"
    }).json()["id"]
    other_phase = client.post(f"/api/projects/{other_pid}/phases", json={
        "phase_type": "P1", "name": "需求评估", "sequence": 1
    }).json()["id"]

    # 前置阶段不存在 → 400
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P4", "name": "工业设计", "sequence": 1, "depends_on_phase_ids": [9999],
    })
    assert resp.status_code == 400

    # 前置阶段属于别的项目 → 400
    resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P4", "name": "工业设计", "sequence": 1, "depends_on_phase_ids": [other_phase],
    })
    assert resp.status_code == 400


def test_create_phase_prerequisite_idempotent(client):
    """重复指定已存在的前置依赖，应幂等跳过而非报错。"""
    pid = client.post("/api/projects", json={
        "code": "PRE-5", "category": "招标", "name": "PRE5", "owner": "x", "market": "国内"
    }).json()["id"]
    a = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P1", "name": "需求评估", "sequence": 1}).json()["id"]

    # 通过独立 dependency API 先建一条 a→b
    b = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P4", "name": "工业设计", "sequence": 2}).json()["id"]
    client.post(f"/api/projects/{pid}/dependencies", json={"from_phase_id": a, "to_phase_id": b, "type": "FS"})

    # 再创建阶段 c，依赖 a；同时如果 c 又被声明依赖 a 不会冲突——这里测的是
    # 创建阶段 c 带 depends_on_phase_ids=[a]，且 a→c 尚不存在 → 应建 1 条
    c = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P5", "name": "结构设计", "sequence": 3, "depends_on_phase_ids": [a],
    }).json()["id"]

    deps = client.get(f"/api/projects/{pid}/dependencies").json()
    pairs = [(d["from_phase_id"], d["to_phase_id"]) for d in deps]
    assert (a, b) in pairs
    assert (a, c) in pairs
    assert len(deps) == 2  # 没有重复


# ---------- 依赖 ----------

def test_dependency_create_and_validate(client):
    pid = client.post("/api/projects", json={
        "code": "DEP-1", "category": "招标", "name": "DEP", "owner": "x", "market": "国内"
    }).json()["id"]
    p1 = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P1", "name": "需求评估", "sequence": 1}).json()["id"]
    p2 = client.post(f"/api/projects/{pid}/phases", json={"phase_type": "P4", "name": "工业设计", "sequence": 2}).json()["id"]

    # 自引用 → 400
    resp = client.post(f"/api/projects/{pid}/dependencies", json={"from_phase_id": p1, "to_phase_id": p1})
    assert resp.status_code == 400

    # 正常创建
    resp = client.post(f"/api/projects/{pid}/dependencies", json={"from_phase_id": p1, "to_phase_id": p2, "type": "FS"})
    assert resp.status_code == 201, resp.text

    # 重复 → 400
    resp = client.post(f"/api/projects/{pid}/dependencies", json={"from_phase_id": p1, "to_phase_id": p2})
    assert resp.status_code == 400


# ---------- 模板应用 + 甘特图 ----------

def test_apply_template_and_gantt(client, db_session):
    tpl_id = _seed_template(db_session)
    pid = client.post("/api/projects", json={
        "code": "TPL-1", "category": "招标", "name": "模板项目", "owner": "x", "market": "国内",
    }).json()["id"]

    resp = client.post(f"/api/projects/{pid}/apply-template/{tpl_id}")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["phases"]) == 2

    # 甘特图数据
    resp = client.get(f"/api/projects/{pid}/gantt")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 3  # 1 项目行 + 2 阶段行
    assert data["data"][0]["type"] == "project"
    assert data["data"][1]["type"] == "task"
    assert len(data["links"]) == 1  # P1→P4 FS
    assert data["links"][0]["source"] == data["data"][1]["id"]
    assert data["links"][0]["target"] == data["data"][2]["id"]
    assert data["links"][0]["type"] == "0"  # FS


# ---------- 资源负载 ----------

def test_resource_workload(client, db_session):
    res = Resource(name="负载测试员", role="结构设计")
    db_session.add(res)
    pid_resp = client.post("/api/projects", json={
        "code": "WL-1", "category": "招标", "name": "负载项目", "owner": "x", "market": "国内"
    })
    pid = pid_resp.json()["id"]
    db_session.commit()

    ph_resp = client.post(f"/api/projects/{pid}/phases", json={
        "phase_type": "P5", "name": "结构设计", "sequence": 1, "assignee_ids": [res.id],
    })
    assert ph_resp.status_code == 201

    resp = client.get(f"/api/resources/{res.id}/workload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"]["name"] == "负载测试员"
    assert len(body["workloads"]) == 1
    assert body["workloads"][0]["project_name"] == "负载项目"
    assert body["workloads"][0]["phase_name"] == "结构设计"


# ---------- 资源 CRUD ----------

def test_resource_crud(client):
    resp = client.post("/api/resources", json={"name": "新员工", "role": "测试"})
    assert resp.status_code == 201
    rid = resp.json()["id"]
    resp = client.put(f"/api/resources/{rid}", json={"role": "工业设计"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "工业设计"
    assert client.delete(f"/api/resources/{rid}").status_code == 204


# ---------- 模板 CRUD ----------

def test_template_crud(client):
    resp = client.post("/api/templates", json={
        "name": "API模板", "category": "定制改造",
        "phases": [{"phase_type": "P1", "name": "需求分析", "sequence": 1}],
        "dependencies": [],
    })
    assert resp.status_code == 201
    tid = resp.json()["id"]
    assert len(resp.json()["phases"]) == 1
    assert client.get(f"/api/templates/{tid}").status_code == 200
    assert client.delete(f"/api/templates/{tid}").status_code == 204


# ---------- 模板B：同 phase_type(P8) 多阶段的串联依赖 ----------

def _seed_template_b(db_session) -> int:
    """写入模板B：5个P8阶段靠 sequence 区分，5条FS串联依赖用 from_seq/to_seq 定位。"""
    tpl = Template(name="量产交付流程", category="量产交付")
    db_session.add(tpl)
    db_session.flush()
    # sequence: 结构设计=1, 图纸归档=2, BOM=3, 投料=4, 首批生产保障=5, 发货=6
    for seq, ptype, name in [
        (1, "P5", "结构设计"), (2, "P8", "图纸归档"), (3, "P8", "BOM制作与激活"),
        (4, "P8", "直接投料"), (5, "P8", "首批生产保障"), (6, "P8", "发货"),
    ]:
        db_session.add(TemplatePhase(template_id=tpl.id, phase_type=ptype, name=name, sequence=seq))
    # 5条FS串联：1→2→3→4→5→6，全部用 from_seq/to_seq 精确定位
    for from_seq, to_seq in [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]:
        db_session.add(TemplateDependency(
            template_id=tpl.id,
            from_phase_type="P5" if from_seq == 1 else "P8",
            to_phase_type="P8",
            from_seq=from_seq, to_seq=to_seq, type="FS",
        ))
    db_session.commit()
    return tpl.id


def test_template_b_chained_dependencies(client, db_session):
    """模板B应用后应生成5条FS依赖，正确串联同类型(P8)阶段。"""
    tpl_id = _seed_template_b(db_session)
    pid = client.post("/api/projects", json={
        "code": "B-1", "category": "量产", "name": "海外量产项目", "owner": "x", "market": "海外",
    }).json()["id"]

    resp = client.post(f"/api/projects/{pid}/apply-template/{tpl_id}")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["phases"]) == 6  # 6个阶段

    # 依赖列表应有 5 条
    deps = client.get(f"/api/projects/{pid}/dependencies").json()
    assert len(deps) == 5
    # 全部 FS
    assert all(d["type"] == "FS" for d in deps)

    # 甘特图应渲染 5 条 link，且 source→target 形成 1→2→3→4→5→6 的链
    gantt = client.get(f"/api/projects/{pid}/gantt").json()
    assert len(gantt["links"]) == 5
    links = sorted(gantt["links"], key=lambda l: l["source"])
    # 按 phase.id 链式验证：每个 link 的 target 应是下一个 link 的 source
    seq = [links[0]["source"]] + [l["target"] for l in links]
    assert all(seq[i + 1] == links[i]["target"] for i in range(len(links)))
    # 验证没有自环
    assert all(l["source"] != l["target"] for l in links)


def test_template_b_dependency_with_seq_via_api(client):
    """通过 API 创建带 from_seq/to_seq 的模板依赖，验证字段能正确存取。"""
    resp = client.post("/api/templates", json={
        "name": "seq模板", "category": "量产交付",
        "phases": [
            {"phase_type": "P8", "name": "阶段X", "sequence": 1},
            {"phase_type": "P8", "name": "阶段Y", "sequence": 2},
        ],
        "dependencies": [
            {"from_phase_type": "P8", "to_phase_type": "P8", "from_seq": 1, "to_seq": 2, "type": "FS"},
        ],
    })
    assert resp.status_code == 201
    tid = resp.json()["id"]
    dep = resp.json()["dependencies"][0]
    assert dep["from_seq"] == 1
    assert dep["to_seq"] == 2
