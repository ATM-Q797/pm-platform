"""冲突手动消除测试（CONFLICT_MODEL_V2 §四 用例 1-10）。

覆盖：P8 排除 / 共担者不连带标 ⚠ / 并行按资源生效 / override 粒度与撤销 /
reason 必填 / a,b 归一化 / 热力图 ⚠ 消失但格值不变 / 权限 403 / 409 / 400 / 404。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.core.security import hash_password
from app.models import Phase, Project, Resource, User


# ---- 公共构造 ----


def _mk_project(db_session, name: str, **kw) -> Project:
    p = Project(code=f"{name}-{len(list(db_session.query(Project))) + 1}", category="新需求",
                name=name, owner="张三", market="拉美区", **kw)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, start: date, end: date,
              phase_type: str = "P4", status: str = "进行中") -> Phase:
    ph = Phase(project_id=project.id, phase_type=phase_type, name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50)
    db_session.add(ph)
    db_session.flush()
    return ph


def _mk_resource(db_session, name: str) -> Resource:
    r = Resource(name=name)
    db_session.add(r)
    db_session.flush()
    return r


def _add_parallel(db_session, r: Resource, n: int, start: date, end: date) -> None:
    """给资源追加 n 个干扰阶段：短段嵌在 [start, end] 头/尾（与 a/b 重叠 <10 天
    → 不构成额外冲突对；头尾两段互相错开 → 也不互撞），但都与重叠区间相交
    → 把并行数推过 _MAX_PARALLEL=3。"""
    spans = [(start, start + timedelta(days=5)), (end - timedelta(days=6), end)]
    for i in range(n):
        p = _mk_project(db_session, f"并行{i + 1}")
        s, e = spans[i % 2]
        ph = _mk_phase(db_session, p, f"并行阶段{i + 1}", s, e)
        ph.assignees = [r]


def _mk_conflict(db_session, name: str, start=date(2026, 7, 1), end=date(2026, 7, 31)):
    """构造恰好报**一对**冲突的资源：a/b 全窗深度重叠 + 2 个头尾干扰段（并行=4）。

    干扰段与 a/b 重叠仅 5~6 天（<10 下限）→ 不构成额外冲突对，
    但都与 a∩b 重叠区间相交 → 并行数 4 > 3 → a-b 这一对报冲突。
    返回 (resource, phase_a, phase_b)。
    """
    r = _mk_resource(db_session, name)
    p1 = _mk_project(db_session, f"{name}项目甲")
    p2 = _mk_project(db_session, f"{name}项目乙")
    a = _mk_phase(db_session, p1, f"{name}阶段甲", start, end)
    b = _mk_phase(db_session, p2, f"{name}阶段乙", start, end)
    a.assignees = [r]
    b.assignees = [r]
    _add_parallel(db_session, r, 2, start, end)
    return r, a, b


def _pairs_of(client, resource_id: int) -> list[tuple[int, int]]:
    """从 /conflicts 提取该资源的归一化冲突对集合。"""
    data = client.get("/api/resources/conflicts").json()
    row = next((d for d in data if d["resource_id"] == resource_id), None)
    if row is None:
        return []
    return [(min(c["phase_a_id"], c["phase_b_id"]), max(c["phase_a_id"], c["phase_b_id"]))
            for c in row["conflicts"]]


def _override(client, resource_id: int, a: int, b: int, reason: str = "并行任务多但工作量小"):
    return client.post(
        f"/api/resources/conflicts/{resource_id}/override",
        json={"phase_a_id": a, "phase_b_id": b, "reason": reason},
    )


# ---- 用例 1：P8 排除 ----


def test_1_p8_excluded_from_conflict_but_counted_in_heatmap(client, db_session):
    """用例 1：P8 阶段与 P5 深度重叠 → 不产生冲突对；热力图 P8 仍占格。"""
    r = _mk_resource(db_session, "交付人")
    p5 = _mk_project(db_session, "P5项目")
    p8 = _mk_project(db_session, "P8项目")
    a = _mk_phase(db_session, p5, "结构设计", date(2026, 7, 1), date(2026, 7, 31), phase_type="P5")
    b = _mk_phase(db_session, p8, "交付", date(2026, 7, 1), date(2026, 7, 31), phase_type="P8")
    a.assignees = [r]
    b.assignees = [r]
    # P8 排除后该资源仅剩 1 个可冲突阶段 → 无冲突对
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []

    # 热力图：P8 仍占格（忙碌度保留）——用绝对日期窗口覆盖 2026-07
    hm = client.get("/api/resources/heatmap", params={"weeks": 0}).json()
    row = next(p for p in hm["people"] if p["resource_id"] == r.id)
    all_entries = [e for cp in row["cell_phases"] if cp for e in cp]
    names = {e["phase_name"] for e in all_entries}
    assert "交付" in names  # P8 占格
    assert all(e["conflict"] is False for e in all_entries)  # 不标 ⚠


# ---- 用例 2 + 3：人员并行视角（回归用户真实案例） ----


def test_2_3_parallel_by_resource_shared_pair(client, db_session):
    """用例 2/3：张晓平（并行 2 ≤3）不报；共担者许进权（并行 1）不连带报。

    复刻真实案例：两个项目的 P5 重叠 24 天，一人深度并行（撞车者）、
    一人仅浅并行（共担者）——均不应出现在冲突报告中，热力图也不标 ⚠。
    """
    zhang = _mk_resource(db_session, "张晓平")
    xu = _mk_resource(db_session, "许进权")
    p486 = _mk_project(db_session, "乌兹别克项目")
    p503 = _mk_project(db_session, "阿联酋项目")
    ph486 = _mk_phase(db_session, p486, "P5结构设计", date(2026, 7, 1), date(2026, 7, 31), phase_type="P5")
    ph503 = _mk_phase(db_session, p503, "P5结构设计", date(2026, 7, 7), date(2026, 8, 5), phase_type="P5")
    ph486.assignees = [zhang]           # 张晓平 486 + 503（重叠 24 天，但并行仅 2）
    ph503.assignees = [zhang, xu]       # 许进权只有 503 一个（共担者）
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []  # 并行 2 ≤ 3：不报（张晓平）；并行 1：更不报（许进权）

    hm = client.get("/api/resources/heatmap", params={"weeks": 0}).json()
    for person in hm["people"]:
        entries = [e for cp in person["cell_phases"] if cp for e in cp]
        assert all(e["conflict"] is False for e in entries), person["name"]
        assert all(e["conflict_details"] == [] for e in entries), person["name"]


# ---- 用例 4：并行 4 报冲突 ----


def test_4_parallel_over_limit_reports(client, db_session):
    """用例 4：某资源 4 阶段同窗深度重叠 → 报冲突对（6 对）。"""
    r = _mk_resource(db_session, "撞车人")
    ids = []
    for i in range(4):
        p = _mk_project(db_session, f"四并项目{i + 1}")
        ph = _mk_phase(db_session, p, f"四并阶段{i + 1}", date(2026, 7, 1), date(2026, 7, 31))
        ph.assignees = [r]
        ids.append(ph.id)
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert len(data) == 1
    assert data[0]["resource_name"] == "撞车人"
    assert len(data[0]["conflicts"]) == 6  # C(4,2)
    assert all(c["overlap_days"] == 30 for c in data[0]["conflicts"])


# ---- 用例 5/6/8：override 粒度 / 撤销 / 归一化 ----


def test_5_override_granularity_per_resource(client, db_session):
    """用例 5：override 后该资源该对不再报；其他资源同对仍报。"""
    # 两个资源都在同一对阶段上并行 4 → 都报
    r1, a1, b1 = _mk_conflict(db_session, "消除者")
    r2 = _mk_resource(db_session, "未消除者")
    a1.assignees.append(r2)
    b1.assignees.append(r2)
    _add_parallel(db_session, r2, 2, date(2026, 7, 1), date(2026, 7, 31))
    db_session.commit()

    before = client.get("/api/resources/conflicts").json()
    assert len(before) == 2  # 前置：两人都报（各恰好一对）

    resp = _override(client, r1.id, a1.id, b1.id)
    assert resp.status_code == 201, resp.text

    after = client.get("/api/resources/conflicts").json()
    assert [d["resource_id"] for d in after] == [r2.id]  # r1 报告消失，r2 仍报
    assert (min(a1.id, b1.id), max(a1.id, b1.id)) in _pairs_of(client, r2.id)


def test_6_override_revert_restores(client, db_session):
    """用例 6：撤销 override 后恢复报告。"""
    r, a, b = _mk_conflict(db_session, "撤销人")
    db_session.commit()

    resp = _override(client, r.id, a.id, b.id)
    assert resp.status_code == 201
    ov_id = resp.json()["id"]
    # 恰好一对冲突 → 消除后该资源从报告中完全消失
    assert _pairs_of(client, r.id) == []

    del_resp = client.delete(f"/api/resources/conflicts/overrides/{ov_id}")
    assert del_resp.status_code == 204
    assert _pairs_of(client, r.id) == [(min(a.id, b.id), max(a.id, b.id))]  # 恢复


def test_7_reason_required(client, db_session):
    """用例 7：缺 reason → 422。"""
    r, a, b = _mk_conflict(db_session, "必填人")
    db_session.commit()
    resp = client.post(
        f"/api/resources/conflicts/{r.id}/override",
        json={"phase_a_id": a.id, "phase_b_id": b.id},
    )
    assert resp.status_code == 422


def test_8_ab_order_normalized(client, db_session):
    """用例 8：(a,b) 与 (b,a) 视为同一对：正序提交成功，逆序再提交 409。"""
    r, a, b = _mk_conflict(db_session, "归一人")
    db_session.commit()

    resp = _override(client, r.id, a.id, b.id)  # 正序
    assert resp.status_code == 201
    assert resp.json()["phase_a_id"] == min(a.id, b.id)  # 存储已归一化
    assert resp.json()["phase_b_id"] == max(a.id, b.id)

    resp2 = _override(client, r.id, b.id, a.id)  # 逆序 = 同一对 → 409
    assert resp2.status_code == 409


def test_9_heatmap_conflict_mark_disappears_after_override(client, db_session):
    """用例 9：消除后该资源该阶段格 ⚠ 消失、格值（忙碌度）不变。"""
    r, a, b = _mk_conflict(db_session, "热力人")
    db_session.commit()

    def _hm():
        hm = client.get("/api/resources/heatmap", params={"weeks": 0}).json()
        return next(p for p in hm["people"] if p["resource_id"] == r.id)

    row = _hm()
    a_entries = [e for cp in row["cell_phases"] if cp for e in cp if e["phase_id"] == a.id]
    assert a_entries  # 前置：阶段 a 在热力图中
    assert all(e["conflict"] is True for e in a_entries)  # 消除前标 ⚠
    assert all(len(e["conflict_details"]) >= 1 for e in a_entries)  # 详情一次到位
    detail = a_entries[0]["conflict_details"][0]
    assert detail["overlap_days"] == 30
    # detail 归一化指向冲突对（a/b 谁 id 小在 phase_a_id）
    assert {detail["phase_a_id"], detail["phase_b_id"]} == {a.id, b.id}
    assert detail["partner_phase_name"] == "热力人阶段乙"  # a 的对方是 b
    cells_before = row["cells"]

    resp = _override(client, r.id, a.id, b.id)
    assert resp.status_code == 201

    row2 = _hm()
    a_entries2 = [e for cp in row2["cell_phases"] if cp for e in cp if e["phase_id"] == a.id]
    assert all(e["conflict"] is False for e in a_entries2)  # ⚠ 消失（唯一一对已消除）
    assert all(e["conflict_details"] == [] for e in a_entries2)
    assert row2["cells"] == cells_before  # 格值（忙碌度）不变


def test_9b_all_pairs_overridden_clears_warning(client, db_session):
    """用例 9 补充：该资源全部对消除后 ⚠ 完全消失、格值不变。"""
    r = _mk_resource(db_session, "全消人")
    phs = []
    for i in range(4):
        p = _mk_project(db_session, f"全消项目{i + 1}")
        ph = _mk_phase(db_session, p, f"全消阶段{i + 1}", date(2026, 7, 1), date(2026, 7, 31))
        ph.assignees = [r]
        phs.append(ph)
    db_session.commit()

    def _hm():
        hm = client.get("/api/resources/heatmap", params={"weeks": 0}).json()
        return next(p for p in hm["people"] if p["resource_id"] == r.id)

    row = _hm()
    assert all(e["conflict"] for cp in row["cell_phases"] if cp for e in cp)
    cells_before = row["cells"]

    # 消除全部 6 对
    from itertools import combinations
    for x, y in combinations(phs, 2):
        resp = _override(client, r.id, x.id, y.id)
        assert resp.status_code == 201, resp.text

    row2 = _hm()
    entries = [e for cp in row2["cell_phases"] if cp for e in cp]
    assert all(e["conflict"] is False for e in entries)  # ⚠ 全消失
    assert all(e["conflict_details"] == [] for e in entries)
    assert row2["cells"] == cells_before  # 格值不变


# ---- 错误语义与权限 ----


def test_duplicate_override_409(client, db_session):
    """重复消除同一对 → 409。"""
    r, a, b = _mk_conflict(db_session, "重复人")
    db_session.commit()
    assert _override(client, r.id, a.id, b.id).status_code == 201
    assert _override(client, r.id, a.id, b.id).status_code == 409


def test_not_conflicting_pair_400(client, db_session):
    """对当前不构成冲突的对 POST → 400。"""
    r, a, b = _mk_conflict(db_session, "错对人")
    p3 = _mk_project(db_session, "错对项目丙")
    c = _mk_phase(db_session, p3, "错对阶段丙", date(2026, 10, 1), date(2026, 10, 30))
    c.assignees = [r]  # 与 a/b 不重叠 → 不构成冲突
    db_session.commit()

    resp = _override(client, r.id, a.id, c.id)
    assert resp.status_code == 400


def test_resource_not_found_404(client, db_session):
    """resource id 不存在 → 404。"""
    r, a, b = _mk_conflict(db_session, "存在人")
    db_session.commit()
    resp = _override(client, 9999, a.id, b.id)
    assert resp.status_code == 404


def test_phase_not_found_404(client, db_session):
    """phase id 不存在 → 404。"""
    r, a, b = _mk_conflict(db_session, "阶段人")
    db_session.commit()
    resp = _override(client, r.id, a.id, 999999)
    assert resp.status_code == 404


def test_override_delete_not_found_404(client, db_session):
    """DELETE 不存在的 override → 404。"""
    assert client.delete("/api/resources/conflicts/overrides/9999").status_code == 404


def test_10_permission_403_for_engineer(client, db_session):
    """用例 10：非 admin/manager 调用 override → 403。"""
    r, a, b = _mk_conflict(db_session, "权限人")
    db_session.add(User(
        username="eng_x", name="工程师甲", role="engineer",
        password_hash=hash_password("testpass"),
    ))
    db_session.commit()

    resp = client.post("/api/auth/login", json={"username": "eng_x", "password": "testpass"})
    assert resp.status_code == 200

    assert _override(client, r.id, a.id, b.id).status_code == 403
    assert client.get("/api/resources/conflicts/overrides").status_code == 403


def test_manager_only_own_projects(client, db_session):
    """manager 仅能消除自己负责项目涉及的资源×阶段对（决策 1）。"""
    r, a, b = _mk_conflict(db_session, "经理人")
    # 张三是默认 owner；建一个 manager 名为张三
    db_session.add(User(
        username="mgr_zhang", name="张三", role="manager",
        password_hash=hash_password("testpass"),
    ))
    # 另一个 manager 李四（不负责任何项目）
    db_session.add(User(
        username="mgr_li", name="李四", role="manager",
        password_hash=hash_password("testpass"),
    ))
    db_session.commit()

    # 李四登录：不负责 a/b 所属项目 → 403
    client.post("/api/auth/login", json={"username": "mgr_li", "password": "testpass"})
    resp = _override(client, r.id, a.id, b.id)
    assert resp.status_code == 403

    # 张三登录：owner 匹配（managed_by 为空回退）→ 201
    client.post("/api/auth/login", json={"username": "mgr_zhang", "password": "testpass"})
    resp = _override(client, r.id, a.id, b.id)
    assert resp.status_code == 201, resp.text


def test_overrides_list_visible_to_manager(client, db_session):
    """GET /conflicts/overrides：manager 可见（决策 3）。"""
    r, a, b = _mk_conflict(db_session, "列表人")
    db_session.add(User(
        username="mgr_list", name="列表经理", role="manager",
        password_hash=hash_password("testpass"),
    ))
    db_session.commit()
    assert _override(client, r.id, a.id, b.id).status_code == 201

    client.post("/api/auth/login", json={"username": "mgr_list", "password": "testpass"})
    resp = client.get("/api/resources/conflicts/overrides")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["resource_id"] == r.id
    assert data[0]["reason"] == "并行任务多但工作量小"
    assert data[0]["phase_a_id"] == min(a.id, b.id)
    assert data[0]["phase_b_id"] == max(a.id, b.id)


def test_override_conflict_detail_partner_direction(client, db_session):
    """conflict_detail.partner 从本人视角指向对方（b 视角 partner 是 a 的项目）。"""
    r = _mk_resource(db_session, "方向人")
    p1 = _mk_project(db_session, "方向项目甲")
    p2 = _mk_project(db_session, "方向项目乙")
    a = _mk_phase(db_session, p1, "方向阶段甲", date(2026, 7, 1), date(2026, 7, 31))
    b = _mk_phase(db_session, p2, "方向阶段乙", date(2026, 7, 1), date(2026, 7, 31))
    a.assignees = [r]
    b.assignees = [r]
    _add_parallel(db_session, r, 2, date(2026, 7, 1), date(2026, 7, 31))
    db_session.commit()

    hm = client.get("/api/resources/heatmap", params={"weeks": 0}).json()
    row = next(p for p in hm["people"] if p["resource_id"] == r.id)
    entries = {e["phase_id"]: e for cp in row["cell_phases"] if cp for e in cp}
    assert entries[a.id]["conflict_details"][0]["partner_name"] == "方向项目乙"
    assert entries[b.id]["conflict_details"][0]["partner_name"] == "方向项目甲"
    assert entries[a.id]["conflict_details"][0]["partner_phase_name"] == "方向阶段乙"
