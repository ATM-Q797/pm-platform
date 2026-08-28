"""资源负载热力矩阵测试（RESOURCE_HEATMAP §四）+ PROJECT_SHELVE §2.5 联动。

覆盖：单元格计数/扫描线 peak/跨桶/状态过滤/搁置排除/缺日期规则/
窗口边界/月粒度/idle/排序/冲突标记/参数 400/半开区间/当前周可见。
日期用相对今天构造，避免时间漂移。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models import Phase, Project, Resource

# ---- 公共构造 ----


def _today() -> date:
    return date.today()


def _mk_project(db_session, name: str, status: str = "进行中") -> Project:
    p = Project(code=f"{name}-{len(list(db_session.query(Project))) + 1}", category="新需求",
                name=name, owner="张三", market="拉美区", status=status)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, start: date | None, end: date | None,
              status: str = "进行中", actual: tuple[date | None, date | None] | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=50)
    if actual is not None:
        ph.actual_start, ph.actual_end = actual
    db_session.add(ph)
    db_session.flush()
    return ph


def _mk_resource(db_session, name: str) -> Resource:
    r = Resource(name=name)
    db_session.add(r)
    db_session.flush()
    return r


def _hm(client, **params) -> dict:
    resp = client.get("/api/resources/heatmap", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _col_index(data: dict, col_date: str) -> int:
    return data["columns"].index(col_date)


def _week_monday(d: date) -> date:
    """d 所在周的周一（与后端桶对齐规则一致）。"""
    return d - timedelta(days=d.weekday())


def _this_week_col(data: dict) -> int:
    """当前周首列 index（本周含在首桶/末桶之一，评审处置 #2）。"""
    return _col_index(data, _week_monday(_today()).isoformat())


# ---- 设计 §四 用例 ----


def test_1_same_week_overlap(client, db_session):
    """用例 1：单人 2 阶段同周重叠 → 该周 cell=2，peak_parallel=2。"""
    t = _today()
    r = _mk_resource(db_session, "重叠人")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    _mk_phase(db_session, p1, "阶段一", t - timedelta(days=1), t + timedelta(days=3))
    _mk_phase(db_session, p2, "阶段二", t - timedelta(days=1), t + timedelta(days=3))
    for ph in db_session.query(Phase):
        ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    row = data["people"][0]
    idx = _this_week_col(data)
    assert row["cells"][idx] == 2
    assert row["peak_parallel"] == 2


def test_1b_same_week_no_overlap(client, db_session):
    """用例 1b：单人 2 阶段同周不重叠（上半周/下半周）→ cell=2，peak_parallel=1（处置 #5）。"""
    t = _today()
    monday = _week_monday(t)
    r = _mk_resource(db_session, "不重叠人")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    _mk_phase(db_session, p1, "上半周", monday, monday + timedelta(days=2))          # 周一~周三
    _mk_phase(db_session, p2, "下半周", monday + timedelta(days=3), monday + timedelta(days=5))  # 周四~周六
    for ph in db_session.query(Phase):
        ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    row = data["people"][0]
    idx = _this_week_col(data)
    assert row["cells"][idx] == 2  # 相交计数：两阶段都与本周桶相交
    assert row["peak_parallel"] == 1  # 扫描线：任意时刻最多 1 个（背靠背不并行）


def test_2_phase_spans_3_weeks(client, db_session):
    """用例 2：阶段跨 3 周（整 21 天）→ 每个相交周桶 +1。"""
    # 从 4 周前的周一开始，保证 3 个周桶都完整落在默认 12 周窗口内
    monday = _week_monday(_today() - timedelta(weeks=4))
    r = _mk_resource(db_session, "跨周人")
    p = _mk_project(db_session, "跨周项目")
    ph = _mk_phase(db_session, p, "三周阶段", monday, monday + timedelta(days=20))  # 10.1-10.21 等价
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    row = data["people"][0]
    idx = _col_index(data, monday.isoformat())
    assert row["cells"][idx] == 1
    assert row["cells"][idx + 1] == 1
    assert row["cells"][idx + 2] == 1


def test_3_done_and_phase_shelved_skipped(client, db_session):
    """用例 3：阶段已完成/已搁置 → 不计入任何桶（进 idle）。"""
    t = _today()
    r = _mk_resource(db_session, "完结人")
    p = _mk_project(db_session, "完结项目")
    ph1 = _mk_phase(db_session, p, "已完成阶段", t, t + timedelta(days=7), status="已完成")
    ph2 = _mk_phase(db_session, p, "已搁置阶段", t, t + timedelta(days=7), status="已搁置")
    ph1.assignees = [r]
    ph2.assignees = [r]
    db_session.commit()

    data = _hm(client)
    assert data["people"] == []
    assert [i["name"] for i in data["idle_people"]] == ["完结人"]


def test_4_project_shelved_skipped(client, db_session):
    """用例 4：项目状态=搁置（含旧值已搁置，双 key）→ 该阶段不计入。"""
    t = _today()
    r = _mk_resource(db_session, "搁置项目人")
    p_new = _mk_project(db_session, "搁置项目", status="搁置")
    p_old = _mk_project(db_session, "旧搁置项目", status="已搁置")
    ph1 = _mk_phase(db_session, p_new, "新搁置阶段", t, t + timedelta(days=7))
    ph2 = _mk_phase(db_session, p_old, "旧搁置阶段", t, t + timedelta(days=7))
    ph1.assignees = [r]
    ph2.assignees = [r]
    db_session.commit()

    data = _hm(client)
    assert data["people"] == []
    assert [i["name"] for i in data["idle_people"]] == ["搁置项目人"]


def test_4b_actual_only_dates_counted(client, db_session):
    """用例 4b：仅实际日期阶段（无计划日期）→ 用 actual_start/actual_end 计入（处置 #4）。"""
    t = _today()
    r = _mk_resource(db_session, "实际日期人")
    p = _mk_project(db_session, "实际项目")
    ph = _mk_phase(db_session, p, "实际阶段", None, None,
                   actual=(t - timedelta(days=1), t + timedelta(days=2)))
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    row = data["people"][0]
    idx = _this_week_col(data)
    assert row["cells"][idx] == 1
    entry = row["cell_phases"][idx][0]
    assert entry["start"] == (t - timedelta(days=1)).isoformat()
    assert entry["end"] == (t + timedelta(days=2)).isoformat()


def test_5_no_dates_not_counted(client, db_session):
    """用例 5：无任何日期阶段（无 plan 且无 actual）→ 不占格。"""
    r = _mk_resource(db_session, "无日期人")
    p = _mk_project(db_session, "无日期项目")
    ph = _mk_phase(db_session, p, "无日期阶段", None, None, actual=(None, None))
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    assert data["people"] == []
    assert [i["name"] for i in data["idle_people"]] == ["无日期人"]


def test_6_window_boundaries(client, db_session):
    """用例 6：窗口 4/12/24 周边界截断 → 桶数与 start/end 正确。"""
    for weeks in (4, 12, 24):
        data = _hm(client, weeks=weeks)
        assert len(data["columns"]) == weeks
        # 窗口 = [start, 今天]，start 为 weeks-1 周前的周一
        expect_start = _week_monday(_today() - timedelta(weeks=weeks - 1))
        assert data["start_date"] == expect_start.isoformat()
        assert data["end_date"] == _today().isoformat()
        # 首桶含 start_date 所在周
        assert data["columns"][0] == expect_start.isoformat()


def test_7_month_granularity(client, db_session):
    """用例 7：granularity=month → 桶按月聚合，label 为月首日。"""
    t = _today()
    r = _mk_resource(db_session, "月桶人")
    p = _mk_project(db_session, "月桶项目")
    ph = _mk_phase(db_session, p, "月桶阶段", t, t + timedelta(days=7))
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client, weeks=4, granularity="month")
    assert data["granularity"] == "month"
    # 4 周窗口 ≈ 当月（可能含上月尾巴）：桶数 1-2，label 均为月首
    assert 1 <= len(data["columns"]) <= 2
    for col in data["columns"]:
        assert col.endswith("-01")
    row = data["people"][0]
    assert sum(row["cells"]) >= 1  # 该阶段至少落在 1 个月桶


def test_8_idle_people(client, db_session):
    """用例 8：零负载人员进 idle_people（按名称排序，处置 #11）。"""
    t = _today()
    busy = _mk_resource(db_session, "忙人")
    _mk_resource(db_session, "周闲")
    _mk_resource(db_session, "陈闲")
    p = _mk_project(db_session, "忙项目")
    ph = _mk_phase(db_session, p, "忙阶段", t, t + timedelta(days=7))
    ph.assignees = [busy]
    db_session.commit()

    data = _hm(client)
    assert [i["name"] for i in data["idle_people"]] == ["周闲", "陈闲"]  # 名称排序
    assert [p_["name"] for p_ in data["people"]] == ["忙人"]


def test_9_sorted_by_peak_parallel(client, db_session):
    """用例 9：排序 peak_parallel 降序 → active_phases 降序。"""
    t = _today()
    # peak=3 人（3 个重叠阶段）
    r3 = _mk_resource(db_session, "三并行")
    for i in range(3):
        p = _mk_project(db_session, f"三并行项目{i + 1}")
        ph = _mk_phase(db_session, p, f"三并行阶段{i + 1}", t, t + timedelta(days=14))
        ph.assignees = [r3]
    # peak=2 人（2 个重叠 + 1 个错开 → active=3）
    r2 = _mk_resource(db_session, "二并行")
    for i in range(2):
        p = _mk_project(db_session, f"二并行项目{i + 1}")
        ph = _mk_phase(db_session, p, f"二并行阶段{i + 1}", t, t + timedelta(days=14))
        ph.assignees = [r2]
    p = _mk_project(db_session, "二并行错开项目")
    ph = _mk_phase(db_session, p, "二并行错开阶段", t + timedelta(days=30), t + timedelta(days=40))
    ph.assignees = [r2]
    # peak=2 但 active=2（排在 active=3 之后）
    r2b = _mk_resource(db_session, "二并行短")
    for i in range(2):
        p = _mk_project(db_session, f"二短项目{i + 1}")
        ph = _mk_phase(db_session, p, f"二短阶段{i + 1}", t, t + timedelta(days=14))
        ph.assignees = [r2b]
    db_session.commit()

    data = _hm(client)
    names = [p_["name"] for p_ in data["people"]]
    assert names == ["三并行", "二并行", "二并行短"]  # 3 → 2(active=3) → 2(active=2)


def test_10_conflict_marked(client, db_session):
    """用例 10：冲突阶段 → cell_phases[].conflict=true（复用 detect_conflicts 冲突集）。"""
    t = _today()
    r = _mk_resource(db_session, "冲突人")
    # 4 个不同项目阶段同窗深度重叠（并行 >3 才报冲突）→ 全部标记
    ids = []
    for i in range(4):
        p = _mk_project(db_session, f"冲突项目{i + 1}")
        ph = _mk_phase(db_session, p, f"冲突阶段{i + 1}", t, t + timedelta(days=30))
        ph.assignees = [r]
        ids.append(ph.id)
    db_session.commit()

    conflicts = client.get("/api/resources/conflicts").json()
    assert conflicts  # detect_conflicts 确认有冲突（前置自检）

    data = _hm(client)
    row = data["people"][0]
    idx = _this_week_col(data)
    entries = row["cell_phases"][idx]
    assert len(entries) == 4
    assert all(e["conflict"] is True for e in entries)  # 4 个阶段都在冲突对里
    assert {e["phase_id"] for e in entries} == set(ids)


def test_10b_conflict_detail_structure(client, db_session):
    """CONFLICT_MODEL_V2 评审处置 #2：conflict_details 数组携带对方阶段/项目/重叠天数/窗口；无冲突空数组。"""
    t = _today()
    r = _mk_resource(db_session, "详情人")
    ps = [_mk_project(db_session, f"详情项目{i + 1}") for i in range(4)]
    phases = [_mk_phase(db_session, ps[i], f"详情阶段{i + 1}", t, t + timedelta(days=30))
              for i in range(4)]
    for ph in phases:
        ph.assignees = [r]
    # 无冲突者（仅 1 个阶段）
    quiet = _mk_resource(db_session, "详情闲人")
    phases[0].assignees.append(quiet)
    db_session.commit()

    data = _hm(client)
    row = next(p for p in data["people"] if p["name"] == "详情人")
    idx = _this_week_col(data)
    entries = row["cell_phases"][idx]
    assert all(e["conflict"] is True for e in entries)
    for e in entries:
        ds = e["conflict_details"]
        assert isinstance(ds, list) and len(ds) >= 1
        d = ds[0]
        assert {"phase_a_id", "phase_b_id", "partner_name", "partner_phase_name",
                "overlap_days", "overlap_start", "overlap_end"} == set(d)
        assert d["overlap_days"] == 30
        assert d["phase_a_id"] < d["phase_b_id"]  # 归一化小 id 在前
        assert e["phase_id"] in (d["phase_a_id"], d["phase_b_id"])

    quiet_row = next(p for p in data["people"] if p["name"] == "详情闲人")
    q_entries = [e for cp in quiet_row["cell_phases"] if cp for e in cp]
    assert all(e["conflict"] is False for e in q_entries)  # 并行 1：不连带标 ⚠
    assert all(e["conflict_details"] == [] for e in q_entries)


def test_10c_shared_pair_not_marked_for_light_parallel_person(client, db_session):
    """CONFLICT_MODEL_V2 §一（回归用户案例）：共担者本人并行 ≤3 → 不标 ⚠。

    撞车者张三（4 并行）报冲突；共担者李四仅参与其中 1~2 个阶段 → 无 ⚠。
    """
    t = _today()
    heavy = _mk_resource(db_session, "撞车共担张三")
    light = _mk_resource(db_session, "共担李四")
    ps = [_mk_project(db_session, f"共担项目{i + 1}") for i in range(4)]
    phases = [_mk_phase(db_session, ps[i], f"共担阶段{i + 1}", t, t + timedelta(days=30))
              for i in range(4)]
    for ph in phases:
        ph.assignees = [heavy]
    # 李四共担其中 2 个阶段（同一对上，但本人并行仅 2 ≤3）
    phases[0].assignees.append(light)
    phases[1].assignees.append(light)
    db_session.commit()

    conflicts = client.get("/api/resources/conflicts").json()
    assert [c["resource_name"] for c in conflicts] == ["撞车共担张三"]  # 李四不报

    data = _hm(client)
    heavy_row = next(p for p in data["people"] if p["name"] == "撞车共担张三")
    heavy_entries = [e for cp in heavy_row["cell_phases"] if cp for e in cp]
    assert all(e["conflict"] is True for e in heavy_entries)
    light_row = next(p for p in data["people"] if p["name"] == "共担李四")
    light_entries = [e for cp in light_row["cell_phases"] if cp for e in cp]
    assert all(e["conflict"] is False for e in light_entries)  # 关键：共担者不连带 ⚠
    assert all(e["conflict_details"] == [] for e in light_entries)


def test_11_invalid_granularity_400(client, db_session):
    """用例 11：非法 granularity（如 'day'）→ 400。"""
    resp = client.get("/api/resources/heatmap", params={"granularity": "day"})
    assert resp.status_code == 400


def test_12_negative_weeks_400(client, db_session):
    """用例 12：weeks 为负数 → 400。"""
    resp = client.get("/api/resources/heatmap", params={"weeks": -1})
    assert resp.status_code == 400


def test_13_weeks_zero_all(client, db_session):
    """用例 13：weeks=0（全部）→ 窗口从数据最早日期起到今天，桶数正确。"""
    today = _today()
    earliest = today - timedelta(days=100)  # 约 15 周前
    r = _mk_resource(db_session, "全窗人")
    p = _mk_project(db_session, "全窗项目")
    ph = _mk_phase(db_session, p, "最早阶段", earliest, earliest + timedelta(days=5))
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client, weeks=0)
    expect_start = _week_monday(earliest)
    assert data["start_date"] == expect_start.isoformat()
    assert data["end_date"] == today.isoformat()
    expect_buckets = (today - expect_start).days // 7 + 1
    assert len(data["columns"]) == expect_buckets
    # 最早阶段在其所在周桶可见
    idx = _col_index(data, expect_start.isoformat())
    assert data["people"][0]["cells"][idx] == 1


def test_14_half_open_interval_not_counted(client, db_session):
    """用例 14：半开区间阶段（仅 plan_start 无 end / 仅 actual 一头）→ 不占格。"""
    t = _today()
    r = _mk_resource(db_session, "半开人")
    p = _mk_project(db_session, "半开项目")
    ph1 = _mk_phase(db_session, p, "只有开始", t, None)
    ph2 = _mk_phase(db_session, p, "只有实际开始", None, None, actual=(t, None))
    ph3 = _mk_phase(db_session, p, "只有结束", None, t + timedelta(days=5))
    for ph in (ph1, ph2, ph3):
        ph.assignees = [r]
    db_session.commit()

    data = _hm(client)
    assert data["people"] == []
    assert [i["name"] for i in data["idle_people"]] == ["半开人"]


def test_15_current_week_visible(client, db_session):
    """用例 15：当前周活跃阶段 → start_date 所在周含在首桶/当前桶，阶段可见（处置 #2）。"""
    t = _today()
    r = _mk_resource(db_session, "本周人")
    p = _mk_project(db_session, "本周项目")
    ph = _mk_phase(db_session, p, "本周阶段", t, t + timedelta(days=2))
    ph.assignees = [r]
    db_session.commit()

    data = _hm(client, weeks=4)
    idx = _this_week_col(data)
    assert idx == len(data["columns"]) - 1  # 4 周窗口：当前周是末桶
    row = data["people"][0]
    assert row["cells"][idx] == 1
    assert row["cell_phases"][idx][0]["phase_name"] == "本周阶段"


# ---- PROJECT_SHELVE §2.5 联动：甘特/热力负载口径一致 ----


def test_shelved_project_excluded_from_workload(client, db_session):
    """SHELVE 联动：搁置项目（双 key）的阶段从 /all/workload 与 /{id}/workload 排除。"""
    t = _today()
    r = _mk_resource(db_session, "联动人")
    p_live = _mk_project(db_session, "活跃项目")
    p_shelved = _mk_project(db_session, "搁置项目", status="搁置")
    p_old = _mk_project(db_session, "旧搁置项目", status="已搁置")
    ph_live = _mk_phase(db_session, p_live, "活跃阶段", t, t + timedelta(days=7))
    ph_shelved = _mk_phase(db_session, p_shelved, "搁置阶段", t, t + timedelta(days=7))
    ph_old = _mk_phase(db_session, p_old, "旧搁置阶段", t, t + timedelta(days=7))
    for ph in (ph_live, ph_shelved, ph_old):
        ph.assignees = [r]
    db_session.commit()

    # /all/workload
    all_wl = client.get("/api/resources/all/workload").json()
    row = next(w for w in all_wl if w["resource"]["id"] == r.id)
    assert [w["phase_name"] for w in row["workloads"]] == ["活跃阶段"]

    # /{resource_id}/workload
    one_wl = client.get(f"/api/resources/{r.id}/workload").json()
    assert [w["phase_name"] for w in one_wl["workloads"]] == ["活跃阶段"]


def test_phase_status_still_filtered_in_workload(client, db_session):
    """SHELVE 回归：阶段级 已完成/已搁置 维持原跳过（与搁置项目排除叠加）。"""
    t = _today()
    r = _mk_resource(db_session, "阶段状态人")
    p = _mk_project(db_session, "阶段状态项目")
    a = _mk_phase(db_session, p, "进行中阶段", t, t + timedelta(days=7))
    b = _mk_phase(db_session, p, "完成阶段", t, t + timedelta(days=7), status="已完成")
    c = _mk_phase(db_session, p, "搁置阶段", t, t + timedelta(days=7), status="已搁置")
    for ph in (a, b, c):
        ph.assignees = [r]
    db_session.commit()

    one_wl = client.get(f"/api/resources/{r.id}/workload").json()
    assert [w["phase_name"] for w in one_wl["workloads"]] == ["进行中阶段"]


def test_heatmap_and_workload_same_scope(client, db_session):
    """验收：热力与甘特同源同口径——搁置项目阶段在两个端点都不出现。"""
    t = _today()
    r = _mk_resource(db_session, "口径人")
    p1 = _mk_project(db_session, "正常项目")
    p2 = _mk_project(db_session, "口径搁置项目", status="搁置")
    ph1 = _mk_phase(db_session, p1, "正常阶段", t, t + timedelta(days=7))
    ph2 = _mk_phase(db_session, p2, "口径搁置阶段", t, t + timedelta(days=7))
    ph1.assignees = [r]
    ph2.assignees = [r]
    db_session.commit()

    hm = _hm(client)
    all_wl = client.get("/api/resources/all/workload").json()
    wl_names = {w["phase_name"] for w in
                next(w for w in all_wl if w["resource"]["id"] == r.id)["workloads"]}
    hm_names = {e["phase_name"]
                for cp in hm["people"][0]["cell_phases"] if cp
                for e in cp}
    assert wl_names == hm_names == {"正常阶段"}



def test_p8_delivery_not_in_resource_views(client, db_session):
    """用户 2026-08-28：P8 交付不占热力格、不在资源负载甘特显示（三处口径统一）。"""
    t = _today()
    r = _mk_resource(db_session, "交付热力人")
    p1 = _mk_project(db_session, "交付项目甲")
    p2 = _mk_project(db_session, "交付项目乙")
    p5 = _mk_phase(db_session, p1, "结构设计", t, t + timedelta(days=7))
    p5.phase_type = "P5"
    p5.assignees = [r]
    p8 = _mk_phase(db_session, p2, "交付", t, t + timedelta(days=7))
    p8.phase_type = "P8"
    p8.assignees = [r]
    db_session.commit()

    hm = _hm(client, weeks=0)
    row = next(p for p in hm["people"] if p["resource_id"] == r.id)
    phase_ids = {e["phase_id"] for cp in row["cell_phases"] if cp for e in cp}
    assert p5.id in phase_ids
    assert p8.id not in phase_ids  # P8 不占格
    assert row["peak_parallel"] == 1  # 只有 P5 计入负载

    all_wl = client.get("/api/resources/all/workload").json()
    me_wl = next(w for w in all_wl if w["resource"]["id"] == r.id)
    assert [w["phase_id"] for w in me_wl["workloads"]] == [p5.id]  # 甘特视图不含 P8
