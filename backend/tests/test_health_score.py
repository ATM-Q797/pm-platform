"""健康度规则灯测试（8-2，2026-11-06 用户裁定模型）：事实触发档位 + 三处同口径。

日期用例基于相对今天构造，避免时间漂移（与 test_dashboard_ext 同模式）。
规则：阶段逾期 ≥7 天→红 / 1–6 天→黄；资源冲突 ≥3 对→黄（<3 不亮）；
无阶段计划日期→灰「未评估」；其余→绿「正常」；搁置不评。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models import ConflictOverride, Phase, Project, Resource  # noqa: F401
from app.schemas import ConflictPair, ResourceConflict
from app.services.health_score import assess_health, assess_projects, longest_overdue_days
from app.services.resource_conflicts import detect_conflicts


def _today() -> date:
    return date.today()


def _mk_project(db_session, name: str, *, plan_start=None, plan_end=None,
                status: str = "进行中", owner: str = "张三") -> Project:
    p = Project(code=str(len(list(db_session.query(Project))) + 1), category="新需求",
                name=name, owner=owner, market="拉美区", status=status,
                plan_start=plan_start, plan_end=plan_end)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, *, start=None, end=None,
              status: str = "进行中", progress: int = 50, rework_count: int = 0) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               plan_start=start, plan_end=end, status=status, progress=progress,
               rework_count=rework_count)
    db_session.add(ph)
    db_session.flush()
    return ph


def _facts(status) -> dict:
    return {f.kind: f for f in status.facts}


# ---------- 阶段逾期事实（≥7 天红 / 1–6 天黄） ----------

def test_overdue_over_7_days_red(db_session):
    """逾期 ≥7 天 → 红档，短语带天数，明细带阶段名与日期。"""
    t = _today()
    p = _mk_project(db_session, "红档项目", plan_start=t - timedelta(days=30),
                    plan_end=t + timedelta(days=30))
    _mk_phase(db_session, p, "配置评估", start=t - timedelta(days=20), end=t - timedelta(days=16))
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "red"
    assert s.reason == "1个阶段逾期16天"
    d = _facts(s)["delay"]
    assert d.severity == 2
    assert "配置评估" in d.detail and "16 天" in d.detail


def test_overdue_7_days_boundary_red(db_session):
    """恰好逾期 7 天 = 红（≥7 分界）。"""
    t = _today()
    p = _mk_project(db_session, "边界项目", plan_start=t - timedelta(days=20),
                    plan_end=t + timedelta(days=20))
    _mk_phase(db_session, p, "甲", start=t - timedelta(days=10), end=t - timedelta(days=7))
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "red" and s.reason == "1个阶段逾期7天"


def test_overdue_6_days_yellow(db_session):
    """逾期 1–6 天 → 黄档（关注）。"""
    t = _today()
    p = _mk_project(db_session, "黄档项目", plan_start=t - timedelta(days=20),
                    plan_end=t + timedelta(days=20))
    _mk_phase(db_session, p, "乙", start=t - timedelta(days=10), end=t - timedelta(days=6))
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "yellow"
    assert s.reason == "1个阶段逾期6天"
    assert _facts(s)["delay"].severity == 1


def test_multiple_overdue_phrases_longest(db_session):
    """多个逾期阶段：短语计数 + 取最长；已完成/搁置阶段不算逾期。"""
    t = _today()
    p = _mk_project(db_session, "多逾期项目", plan_start=t - timedelta(days=40),
                    plan_end=t + timedelta(days=40))
    _mk_phase(db_session, p, "长逾期", start=t - timedelta(days=30), end=t - timedelta(days=16))
    _mk_phase(db_session, p, "短逾期", start=t - timedelta(days=10), end=t - timedelta(days=3))
    _mk_phase(db_session, p, "已完成段", start=t - timedelta(days=50), end=t - timedelta(days=40),
              status="已完成")
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "red"
    assert s.reason == "2个阶段逾期最长16天"
    assert longest_overdue_days(list(p.phases), t) == 16


def test_no_overdue_green(db_session):
    """无逾期无冲突 → 绿「正常」。"""
    t = _today()
    p = _mk_project(db_session, "正常项目", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    _mk_phase(db_session, p, "甲", start=t - timedelta(days=5), end=t + timedelta(days=5))
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "green" and s.reason == "正常"


# ---------- 资源冲突事实（≥3 对才亮） ----------

def _conflict_pair(p: Project, ph, other_p, other_ph, t) -> ConflictPair:
    return ConflictPair(
        phase_a_id=ph.id, phase_a_name=ph.name, project_a_id=p.id, project_a_name=p.name,
        phase_b_id=other_ph.id, phase_b_name=other_ph.name,
        project_b_id=other_p.id, project_b_name=other_p.name,
        overlap_days=10, overlap_start=t, overlap_end=t + timedelta(days=10),
    )


def test_conflict_3_pairs_yellow(db_session):
    """冲突 ≥3 对（去重后）→ 黄「资源冲突3对」；<3 对不亮。"""
    t = _today()
    p = _mk_project(db_session, "冲突项目", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    phases = [_mk_phase(db_session, p, f"甲{i}", start=t, end=t + timedelta(days=10))
              for i in range(3)]
    other = _mk_project(db_session, "对方", plan_start=t - timedelta(days=10),
                        plan_end=t + timedelta(days=10))
    other_ph = _mk_phase(db_session, other, "乙", start=t, end=t + timedelta(days=10))
    pairs = [_conflict_pair(p, ph, other, other_ph, t) for ph in phases]
    conflicts = [ResourceConflict(resource_id=1, resource_name="测试台", conflicts=pairs)]

    s = assess_health(p, list(p.phases), conflicts, t)
    assert s.band == "yellow" and s.reason == "资源冲突3对"
    assert "测试台" in _facts(s)["conflict"].detail

    # 2 对（阈值下）→ 不亮，绿
    s2 = assess_health(p, list(p.phases), [ResourceConflict(
        resource_id=1, resource_name="测试台", conflicts=pairs[:2])], t)
    assert s2.band == "green"


def test_conflict_pairs_deduped(db_session):
    """同一冲突对跨资源重复报告 → 按阶段对去重；去重后 <3 对不亮。"""
    t = _today()
    p = _mk_project(db_session, "去重项目", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    ph1 = _mk_phase(db_session, p, "阶段1", start=t, end=t + timedelta(days=10))
    other = _mk_project(db_session, "对方", plan_start=t - timedelta(days=10),
                        plan_end=t + timedelta(days=10))
    ph2 = _mk_phase(db_session, other, "阶段2", start=t, end=t + timedelta(days=10))
    pair = _conflict_pair(p, ph1, other, ph2, t)
    # 同一对被两个资源各报一次（跨资源重复）→ 去重后 1 对，不亮
    conflicts = [
        ResourceConflict(resource_id=1, resource_name="测试台", conflicts=[pair]),
        ResourceConflict(resource_id=2, resource_name="老化房", conflicts=[pair]),
    ]
    s = assess_health(p, list(p.phases), conflicts, t)
    assert s.band == "green" and s.reason == "正常"


# ---------- 多事实同现 / 档位归并 ----------

def test_red_dominates_and_reason_worst(db_session):
    """红+黄同现 → 红档，reason 取最严重（逾期）；facts 两条都在。"""
    t = _today()
    p = _mk_project(db_session, "混合项目", plan_start=t - timedelta(days=30),
                    plan_end=t + timedelta(days=30))
    ph = _mk_phase(db_session, p, "逾期段", start=t - timedelta(days=20), end=t - timedelta(days=10))
    other = _mk_project(db_session, "对方", plan_start=t - timedelta(days=10),
                        plan_end=t + timedelta(days=10))
    # 3 个不同阶段对（同对去重，必须不同对才达阈值）
    other_phs = [_mk_phase(db_session, other, f"乙{i}", start=t, end=t + timedelta(days=10))
                 for i in range(3)]
    pairs = [_conflict_pair(p, ph, other, oph, t) for oph in other_phs]
    conflicts = [ResourceConflict(resource_id=1, resource_name="测试台", conflicts=pairs)]

    s = assess_health(p, list(p.phases), conflicts, t)
    assert s.band == "red"
    assert s.reason == "1个阶段逾期10天"  # 最严重事实
    assert {f.kind for f in s.facts} == {"delay", "conflict"}


# ---------- 无法判定 / 搁置 ----------

def test_no_plan_dates_gray(db_session):
    """无阶段或阶段均无计划日期 → 灰「未评估」，不冒充绿。"""
    t = _today()
    p1 = _mk_project(db_session, "无阶段项目")
    s1 = assess_health(p1, [], [], t)
    assert s1.band == "gray" and s1.reason == "未评估"
    assert "无阶段" in _facts(s1)["nodata"].detail  # 成因分句：无阶段

    p2 = _mk_project(db_session, "无日期项目")
    _mk_phase(db_session, p2, "甲")  # 无 plan_end
    s2 = assess_health(p2, list(p2.phases), [], t)
    assert s2.band == "gray" and "活跃阶段均无计划日期" in _facts(s2)["nodata"].detail


def test_partial_dates_with_fact_band_plus_note(db_session):
    """部分缺日期 + 有事实 → 事实定档，facts 附注「N 个活跃阶段无计划日期，未纳入判定」。"""
    t = _today()
    p = _mk_project(db_session, "部分缺日期", plan_start=t - timedelta(days=30),
                    plan_end=t + timedelta(days=30))
    _mk_phase(db_session, p, "有日期", end=t - timedelta(days=16))
    _mk_phase(db_session, p, "无日期")  # 活跃但无 plan_end
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "red" and s.reason == "1个阶段逾期16天"
    notes = [f for f in s.facts if f.kind == "nodata"]
    assert len(notes) == 1 and "1 个活跃阶段无计划日期" in notes[0].detail


def test_partial_dates_no_fact_gray_not_green(db_session):
    """无事实但存在无计划日期的活跃阶段 → 灰「未评估」，不冒充正常。"""
    t = _today()
    p = _mk_project(db_session, "覆盖不全", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    _mk_phase(db_session, p, "正常有日期", start=t - timedelta(days=5),
              end=t + timedelta(days=5), status="进行中")
    _mk_phase(db_session, p, "缺日期", status="未开始")
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "gray" and s.reason == "未评估"
    assert "无法判定全貌" in _facts(s)["nodata"].detail


def test_all_phases_done_green(db_session):
    """全部阶段已完成的项目 → 绿「正常」（完成阶段不产生逾期也不计冲突）。"""
    t = _today()
    p = _mk_project(db_session, "已完工", plan_start=t - timedelta(days=30),
                    plan_end=t - timedelta(days=10))
    _mk_phase(db_session, p, "旧阶段", start=t - timedelta(days=30),
              end=t - timedelta(days=20), status="已完成")
    s = assess_health(p, list(p.phases), [], t)
    assert s.band == "green" and s.reason == "正常"


def test_all_phases_done_conflict_not_counted(db_session):
    """完成阶段不计冲突（本层锚）：全完成阶段 + 含该阶段的合成冲突对 → 仍绿「正常」。"""
    t = _today()
    p = _mk_project(db_session, "完工有旧冲突", plan_start=t - timedelta(days=30),
                    plan_end=t - timedelta(days=10))
    done_ph = _mk_phase(db_session, p, "旧阶段", start=t - timedelta(days=30),
                        end=t - timedelta(days=20), status="已完成")
    other = _mk_project(db_session, "对方", plan_start=t - timedelta(days=10),
                        plan_end=t + timedelta(days=10))
    other_ph = _mk_phase(db_session, other, "在办", start=t, end=t + timedelta(days=10))
    pair = _conflict_pair(p, done_ph, other, other_ph, t)
    conflicts = [ResourceConflict(resource_id=1, resource_name="测试台", conflicts=[pair])]
    s = assess_health(p, list(p.phases), conflicts, t)
    assert s.band == "green" and s.reason == "正常"


def test_shelved_project_not_assessed(db_session):
    """搁置项目不评：assess_projects 不返回其 id（调用方显示「—」）。"""
    t = _today()
    _mk_project(db_session, "搁置项目", status="搁置", plan_start=t - timedelta(days=10),
                plan_end=t + timedelta(days=10))
    rows = db_session.query(Project).all()
    result = assess_projects(rows, [], t)
    assert result == {} or all(p.status != "搁置" or p.id not in result for p in rows)


# ---------- 三处同口径（验收：列表/详情/看板同一函数） ----------

def test_list_api_health_and_endpoint_consistency(client, db_session):
    """列表随行 health 与单项目端点同口径同档。"""
    t = _today()
    p = _mk_project(db_session, "一致性接口", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    _mk_phase(db_session, p, "甲", start=t - timedelta(days=20), end=t - timedelta(days=10))
    db_session.commit()

    rows = client.get("/api/projects").json()
    row = next(r for r in rows if r["id"] == p.id)
    assert row["health"] is not None
    single = client.get(f"/api/projects/{p.id}/health").json()
    assert row["health"]["band"] == single["band"] == "red"
    assert row["health"]["reason"] == single["reason"]


def test_dashboard_risk_projects(client, db_session):
    """风险分析弹窗行：红/黄上卡、绿/灰不上、红档在前、逾期久在前。"""
    t = _today()
    bad = _mk_project(db_session, "红档接口项目", plan_start=t - timedelta(days=40),
                      plan_end=t + timedelta(days=40))
    _mk_phase(db_session, bad, "逾期长", start=t - timedelta(days=30), end=t - timedelta(days=20))
    mild = _mk_project(db_session, "黄档接口项目", plan_start=t - timedelta(days=20),
                       plan_end=t + timedelta(days=20))
    _mk_phase(db_session, mild, "逾期短", start=t - timedelta(days=10), end=t - timedelta(days=5))
    good = _mk_project(db_session, "健康接口项目", plan_start=t - timedelta(days=10),
                       plan_end=t + timedelta(days=10))
    _mk_phase(db_session, good, "正常", start=t - timedelta(days=5), end=t + timedelta(days=5))
    _mk_project(db_session, "搁置接口项目", status="搁置", plan_start=t - timedelta(days=10),
                plan_end=t + timedelta(days=10))
    db_session.commit()

    data = client.get("/api/dashboard/stats").json()
    ids = [r["project_id"] for r in data["risk_projects"]]
    assert bad.id in ids and mild.id in ids
    assert good.id not in ids  # 绿不上卡
    bands = [r["band"] for r in data["risk_projects"]]
    assert bands == sorted(bands, key=lambda b: 0 if b == "red" else 1)  # 红在前
    row = next(r for r in data["risk_projects"] if r["project_id"] == bad.id)
    assert row["reason"] == "1个阶段逾期20天"
    assert row["overdue_days"] >= 20


# ---------- 端点门控（评审 #80 线索①修复回归锚） ----------

def test_health_endpoint_shelved_409(client, db_session):
    """搁置项目请求健康度端点 → 409 明示拒绝。"""
    t = _today()
    p = _mk_project(db_session, "搁置端点", status="搁置", plan_start=t,
                    plan_end=t + timedelta(days=10))
    db_session.commit()
    resp = client.get(f"/api/projects/{p.id}/health")
    assert resp.status_code == 409


def test_health_endpoint_404(client, db_session):
    resp = client.get("/api/projects/99999/health")
    assert resp.status_code == 404


def _mk_user(db_session, username: str, role: str, name: str = "测试用户"):
    from app.core.security import hash_password
    from app.models import User
    u = User(username=username, name=name, role=role,
             password_hash=hash_password("testpass"), must_change_password=False)
    db_session.add(u)
    db_session.commit()
    return u


def test_health_endpoint_viewer_200(client, db_session):
    """viewer（看板主力用户）→ 200（读端点与同族一致，仅专项隔离）。"""
    t = _today()
    p = _mk_project(db_session, "viewer可读项目", plan_start=t - timedelta(days=10),
                    plan_end=t + timedelta(days=10))
    _mk_phase(db_session, p, "甲", progress=50)
    _mk_user(db_session, "view_health2", "viewer", "观察员健康2")

    client.post("/api/auth/login", json={"username": "view_health2", "password": "testpass"})
    resp = client.get(f"/api/projects/{p.id}/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["band"] in ("green", "yellow", "red", "gray")


def test_health_endpoint_special_project_engineer_403(client, db_session):
    """专项隔离仍在：engineer 访问专项项目健康度 → 403。"""
    t = _today()
    p = _mk_project(db_session, "专项健康项目")
    p.is_special = True
    _mk_phase(db_session, p, "甲", progress=50)
    _mk_user(db_session, "eng_health2", "engineer", "工程师健康2")

    client.post("/api/auth/login", json={"username": "eng_health2", "password": "testpass"})
    resp = client.get(f"/api/projects/{p.id}/health")
    assert resp.status_code == 403


# ---------- 真实冲突检测口径复用（detect_conflicts 同源） ----------

def test_conflict_fact_with_real_detection(db_session):
    """与 detect_conflicts 真实检测同源：深度重叠阶段对按项目去重计数。"""
    t = _today()
    ra = Resource(name="冲突资源乙", role="工业设计")
    db_session.add(ra)
    pa = _mk_project(db_session, "项目甲", plan_start=t - timedelta(days=60),
                     plan_end=t + timedelta(days=60))
    pb = _mk_project(db_session, "项目乙", plan_start=t - timedelta(days=60),
                     plan_end=t + timedelta(days=60))
    common = dict(start=t - timedelta(days=10), end=t + timedelta(days=10))
    phs = [
        _mk_phase(db_session, pa, "甲-1", **common),
        _mk_phase(db_session, pa, "甲-2", **common),
        _mk_phase(db_session, pb, "乙-1", **common),
        _mk_phase(db_session, pb, "乙-2", **common),
    ]
    from app.models.phase import phase_assignee
    from sqlalchemy import insert
    for ph in phs:
        db_session.execute(insert(phase_assignee).values(phase_id=ph.id, resource_id=ra.id))
    db_session.commit()

    conflicts = detect_conflicts(db_session)
    assert conflicts, "测试前置：应检出冲突"
    s = assess_health(pa, list(pa.phases), conflicts, t)
    # 甲内部 1 对（甲-1×甲-2）+ 甲乙间 4 对 = 5 对 ≥3 → 黄（无逾期）
    assert s.band == "yellow" and s.reason.startswith("资源冲突")
