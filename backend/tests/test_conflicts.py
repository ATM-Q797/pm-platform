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


def test_overlap_detected(client, db_session):
    """同一资源跨项目重叠：检测出冲突与重叠天数。"""
    r = _mk_resource(db_session, "李四")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 20))
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 10), date(2026, 7, 30))
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    resp = client.get("/api/resources/conflicts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["resource_name"] == "李四"
    pairs = data[0]["conflicts"]
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["overlap_days"] == 10  # 7-10 ~ 7-20 重叠 10 天
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
    a = _mk_phase(db_session, p1, "结构设计", date(2026, 7, 1), date(2026, 7, 20))
    b = _mk_phase(db_session, p2, "样机打样", date(2026, 7, 10), date(2026, 7, 30))
    a.assignees = [r]
    b.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert len(data[0]["conflicts"]) == 1


def test_three_way_overlap_sorted_by_days(client, db_session):
    """多冲突排序：重叠天数降序（最严重在前）。"""
    r = _mk_resource(db_session, "吴十")
    p1 = _mk_project(db_session, "项目甲")
    p2 = _mk_project(db_session, "项目乙")
    p3 = _mk_project(db_session, "项目丙")
    a = _mk_phase(db_session, p1, "阶段一", date(2026, 7, 1), date(2026, 7, 30))   # 与 b 重叠 20 天
    b = _mk_phase(db_session, p2, "阶段二", date(2026, 7, 10), date(2026, 8, 10))  # 与 c 重叠 9 天
    c = _mk_phase(db_session, p3, "阶段三", date(2026, 8, 1), date(2026, 8, 20))   # 与 a 不重叠
    a.assignees = [r]
    b.assignees = [r]
    c.assignees = [r]
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    pairs = data[0]["conflicts"]
    assert len(pairs) == 2  # a-b、b-c
    assert pairs[0]["overlap_days"] == 20  # 最严重的在前
    assert pairs[1]["overlap_days"] == 9


def test_unassigned_resource_no_conflict(client, db_session):
    """无分配阶段的资源不出现在结果中。"""
    _mk_resource(db_session, "闲人")
    db_session.commit()

    data = client.get("/api/resources/conflicts").json()
    assert data == []
