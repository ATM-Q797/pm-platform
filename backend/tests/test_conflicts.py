"""资源冲突检测测试。

覆盖：重叠检测/背靠背不冲突/同项目不冲突/缺日期跳过/已完成跳过/去重/API 结构。
"""
from __future__ import annotations

from datetime import date

from app.models import Phase, Project, Resource


def _mk_project(db_session, name: str) -> Project:
    p = Project(code=str(len(list(db_session.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区")
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


def _mk_resource(db_session, name: str) -> Resource:
    r = Resource(name=name)
    db_session.add(r)
    db_session.flush()
    return r


def _add_parallel(db_session, r: Resource, n: int, start: date, end: date) -> None:
    """给资源追加 n 个不同项目的活跃阶段（同一时间窗口），用于把并行数推过阈值。"""
    for i in range(n):
        p = _mk_project(db_session, f"并行项目{i + 1}")
        ph = _mk_phase(db_session, p, f"并行阶段{i + 1}", start, end)
        ph.assignees = [r]


def test_overlap_detected(client, db_session):
    """深度重叠（≥10 天 且 ≥较短工期 60%）：检测出冲突与重叠天数。"""
    r = _mk_resource(db_session, "李四")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    # a 30 天（7-1~7-30）、b 21 天（7-10~7-30）：重叠 20 天 ≥ 10 且 ≥ 21*0.6=12.6 ✅
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 30))
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 10), date(2026, 7, 30))
    a.assignees = [r]
    b.assignees = [r]
    # 并行数推到 4（2 冲突阶段 + 2 干扰阶段在同一窗口）→ 超过并行上限，报冲突
    _add_parallel(db_session, r, 2, date(2026, 7, 1), date(2026, 7, 30))
    db_session.commit()

    resp = client.get("/api/resources/conflicts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["resource_name"] == "李四"
    pairs = data[0]["conflicts"]
    # 4 个阶段两两组合 = 6 对（2 冲突阶段 + 2 干扰阶段互相也构成冲突）
    assert len(pairs) == 6
    pair = pairs[0]
    assert pair["overlap_days"] in (20, 21, 29, 30)
    assert pair["project_a_name"] == "项目甲" or pair["project_a_name"] == "项目乙"
    assert pair["phase_a_name"] in ("结构设计", "样机打样")


def test_back_to_back_not_conflict(client, db_session):
    """背靠背（end == start）不算冲突。"""
    r = _mk_resource(db_session, "王五")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 10))
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 10), date(2026, 7, 30))
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_same_project_not_conflict(client, db_session):
    """同项目的两个阶段不算冲突（正常分工）。"""
    r = _mk_resource(db_session, "赵六")
    p1 = _mk_project(db_session, "项目甲")
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 20))
    b = _mk_phase(db_session, p1, "样机打样", date(2026, 7, 10), date(2026, 7, 30))
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_missing_date_skipped(client, db_session):
    """缺日期阶段跳过。"""
    r = _mk_resource(db_session, "钱七")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 20))
    b = Phase(project_id=p2.id, phase_type="P5", name="样机打样", sequence=1,
              plan_start=None, plan_end=None, status="进行中", progress=0)
    db_session.add(b)
    db_session.flush()
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_done_and_blocked_skipped(client, db_session):
    """已完成/已搁置阶段跳过。"""
    r = _mk_resource(db_session, "孙八")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 20), status="已完成")
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 10), date(2026, 7, 30), status="已搁置")
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_pair_reported_once(client, db_session):
    """同一对阶段只报一次（i<j 遍历天然去重）。"""
    r = _mk_resource(db_session, "周九")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    # 重叠 20 天（30 天与 21 天阶段）→ 深度足够
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 30))
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 8), date(2026, 7, 28))
    a.assignees = [r]
    b.assignees = [r]
    # 并行数推到 4 → 报冲突
    _add_parallel(db_session, r, 2, date(2026, 7, 1), date(2026, 7, 30))
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    # 4 个阶段 = 6 对，每对只出现一次（i<j 天然去重）
    assert len(data) == 1
    assert len(data[0]["conflicts"]) == 6
    ids = [(c["phase_a_id"], c["phase_b_id"]) for c in data[0]["conflicts"]]
    assert len(ids) == len(set(ids))  # 无重复对


def test_three_way_overlap_sorted_by_days(client, db_session):
    """多冲突排序：重叠天数降序（最严重在前）；深度不足的不算冲突。"""
    r = _mk_resource(db_session, "吴十")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    p3 = _mk_project(db_session, "项目丙")
    a = _mk_phase(db_session, p1, "阶段一", date(2026, 7, 1), date(2026, 7, 30))   # 与 b 重叠 20 天（≥10 且 ≥18 ✅）
    b = _mk_phase(db_session, p2, "阶段二", date(2026, 7, 10), date(2026, 8, 10))  # 与 c 重叠 9 天（<10 ❌）
    c = _mk_phase(db_session, p3, "阶段三", date(2026, 8, 1), date(2026, 8, 20))   # 与 a 不重叠
    a.assignees = [r]
    b.assignees = [r]
    c.assignees = [r]
    # 并行数推到 5（a-b 重叠窗口 7-10~7-30 内活跃 = a,b,+2 干扰）→ 报冲突
    _add_parallel(db_session, r, 2, date(2026, 7, 1), date(2026, 7, 30))
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    pairs = data[0]["conflicts"]
    # 活跃窗口内的 4 个阶段（a、b、2 干扰）两两组合 = 6 对；
    # c 与 a 不重叠、与 b 重叠 9 天 <10 下限 → 不计入
    assert len(pairs) == 6
    assert all(p["overlap_days"] >= 10 for p in pairs)
    assert max(p["overlap_days"] for p in pairs) == 29  # 干扰阶段(30天) × a(30天) 重叠 29 天最严重


def test_shallow_overlap_not_conflict(client, db_session):
    """浅重叠不算冲突：重叠 < 10 天下限 或 < 较短阶段工期 60%（项目并行是常态）。"""
    r = _mk_resource(db_session, "郑浅")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    # 两个 30 天阶段，重叠 10 天（7-20~7-30）→ 10 ≥ 10 但 < 18（30 天 60%）→ 不算冲突
    a = _mk_phase(db_session, p1, "阶段甲", date(2026, 7, 1), date(2026, 7, 30))
    b = _mk_phase(db_session, p2, "阶段乙", date(2026, 7, 20), date(2026, 8, 18))
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []  # 10 天 < 18 天（60%）→ 深度不足


def test_deep_overlap_short_phase_conflict(client, db_session):
    """短阶段几乎被整段占用（≥10 天且 ≥60%）且并行超限 → 深度足够，算冲突。"""
    r = _mk_resource(db_session, "冯深")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    # 长阶段 30 天；短阶段 12 天完全落在长阶段窗口内 → 重叠 12 天 ≥ 10 且 ≥ 7.2 → 冲突
    a = _mk_phase(db_session, p1, "长阶段", date(2026, 7, 1), date(2026, 7, 30))
    b = _mk_phase(db_session, p2, "短阶段", date(2026, 7, 10), date(2026, 7, 22))
    a.assignees = [r]
    b.assignees = [r]
    # 并行数推到 4 → 报冲突
    _add_parallel(db_session, r, 2, date(2026, 7, 1), date(2026, 7, 30))
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert len(data) == 1
    assert len(data[0]["conflicts"]) == 6  # 4 阶段两两组合
    assert any(c["overlap_days"] == 12 for c in data[0]["conflicts"])  # a-b 对存在


def test_parallel_within_limit_not_conflict(client, db_session):
    """并行 ≤3：即使深度重叠也不报冲突（用户确认：3 个并行是正常状态）。"""
    r = _mk_resource(db_session, "蒋三")
    # 3 个阶段（3 个项目）在 7-1~7-30 窗口内两两深度重叠（31 天×3 互叠）
    for i in range(3):
        p = _mk_project(db_session, f"三并行项目{i + 1}")
        ph = _mk_phase(db_session, p, f"三并行阶段{i + 1}", date(2026, 7, 1), date(2026, 8, 1))
        ph.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []  # 并行数 3 ≤ 3 → 不报


def test_parallel_over_limit_conflict(client, db_session):
    """并行 ≥4：深度重叠时报冲突。"""
    r = _mk_resource(db_session, "沈四")
    for i in range(4):
        p = _mk_project(db_session, f"四并行项目{i + 1}")
        ph = _mk_phase(db_session, p, f"四并行阶段{i + 1}", date(2026, 7, 1), date(2026, 8, 1))
        ph.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    # 4 个阶段两两组合：C(4,2) = 6 对冲突
    assert len(data) == 1
    assert len(data[0]["conflicts"]) == 6
    assert all(c["overlap_days"] == 31 for c in data[0]["conflicts"])


def test_unassigned_resource_no_conflict(client, db_session):
    """无分配阶段的资源不出现在结果中。"""
    _mk_resource(db_session, "闲人")
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_p8_phase_excluded_from_conflict(client, db_session):
    """CONFLICT_MODEL_V2 §2.1：P8 交付不参与冲突对生成（热力图计数保留在热力测覆盖）。"""
    r = _mk_resource(db_session, "交付排除人")
    p1 = _mk_project(db_session, "P8甲项目")
    p2 = _mk_project(db_session, "P8乙项目")
    # 4 个 P8 阶段同窗深度重叠（若无 P8 排除会是 C(4,2)=6 对冲突）
    for i in range(4):
        ph = _mk_phase(db_session, p1 if i % 2 == 0 else p2, f"交付阶段{i + 1}",
                       date(2026, 7, 1), date(2026, 7, 31))
        ph.phase_type = "P8"
        ph.assignees = [r]
    # 同项目跳过 + P8 排除 → 无任何冲突对；再补一个 P5 与 P8 重叠也不报
    p3 = _mk_project(db_session, "P5项目")
    p5 = _mk_phase(db_session, p3, "结构设计", date(2026, 7, 1), date(2026, 7, 31))
    p5.phase_type = "P5"
    p5.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []


def test_override_excluded_from_conflicts(client, db_session):
    """CONFLICT_MODEL_V2 §2.3：override 后该资源该对不再报（其余资源仍报）。"""
    from app.models import ConflictOverride

    r1 = _mk_resource(db_session, "消除回归人")
    r2 = _mk_resource(db_session, "保留回归人")
    p1 = _mk_project(db_session, "回归甲")
    p2 = _mk_project(db_session, "回归乙")
    a = _mk_phase(db_session, p1, "回归阶段甲", date(2026, 7, 1), date(2026, 7, 31))
    b = _mk_phase(db_session, p2, "回归阶段乙", date(2026, 7, 1), date(2026, 7, 31))
    a.assignees = [r1, r2]
    b.assignees = [r1, r2]
    # 各自补 2 个短干扰段推并行（头尾 5/6 天 <10 不构成额外对）
    for r in (r1, r2):
        q1 = _mk_project(db_session, f"干扰A{r.id}")
        q2 = _mk_project(db_session, f"干扰B{r.id}")
        _mk_phase(db_session, q1, "干扰一", date(2026, 7, 1), date(2026, 7, 6)).assignees = [r]
        _mk_phase(db_session, q2, "干扰二", date(2026, 7, 25), date(2026, 7, 31)).assignees = [r]
    db_session.commit()

    before = client.get("/api/resources/conflicts").json()
    assert len(before) == 2

    # 归一化小 id 在前写入（(b,a) 逆序写也应命中 (a,b)）
    db_session.add(ConflictOverride(
        resource_id=r1.id,
        phase_a_id=max(a.id, b.id),
        phase_b_id=min(a.id, b.id),
        reason="并行任务多但工作量小",
    ))
    db_session.commit()

    after = client.get("/api/resources/conflicts").json()
    assert [d["resource_id"] for d in after] == [r2.id]
