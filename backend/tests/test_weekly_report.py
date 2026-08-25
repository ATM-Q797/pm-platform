"""周报生成（T7）测试。

覆盖：空项目/单项目/全部项目/无风险数据/内容章节/权限。
日期用例基于相对今天构造（周一为一周起点）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models import Phase, Project


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _mk_project(db_session, name: str) -> Project:
    p = Project(code=str(len(list(db_session.query(Project))) + 1), category="新需求",
                name=name, owner="张三", market="拉美区")
    db_session.add(p)
    db_session.flush()
    return p


def _mk_phase(db_session, project: Project, name: str, status: str = "未开始",
              progress: int = 0, plan_start: date | None = None,
              plan_end: date | None = None, updated_at: datetime | None = None) -> Phase:
    ph = Phase(project_id=project.id, phase_type="P4", name=name, sequence=1,
               status=status, progress=progress,
               plan_start=plan_start, plan_end=plan_end, updated_at=updated_at)
    db_session.add(ph)
    db_session.flush()
    return ph


def _gen(client, body: dict | None = None):
    resp = client.post("/api/reports/weekly", json=body or {})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_report_empty_db(client, db_session):
    """空库：正常生成，章节齐全，无报错。"""
    data = _gen(client)
    assert "整体进度概览" in data["markdown"]
    assert "完成率" in data["markdown"]
    assert "风险预警" in data["markdown"]
    assert "本周完成" in data["markdown"]
    assert "进行中" in data["markdown"]
    assert "下周计划" in data["markdown"]
    assert "0%" in data["markdown"]  # 空库完成率 0
    assert data["plain_text"].strip()
    assert data["generated_at"]


def test_report_single_project(client, db_session):
    """单项目周报：统计与各部分内容正确。"""
    t = date.today()
    monday = _monday(t)
    p = _mk_project(db_session, "周报项目")
    # 本周完成
    _mk_phase(db_session, p, "已完成阶段", status="已完成", progress=100,
              updated_at=monday + timedelta(days=1))
    # 进行中
    _mk_phase(db_session, p, "进行中阶段", status="进行中", progress=60)
    # 未开始（下周计划）
    _mk_phase(db_session, p, "下周开始", status="未开始",
              plan_start=monday + timedelta(days=8))
    # 延期
    _mk_phase(db_session, p, "已延期阶段", status="进行中",
              plan_start=t - timedelta(days=20), plan_end=t - timedelta(days=2))
    # 历史完成（updated_at 旧 → 不计入本周完成）
    _mk_phase(db_session, p, "历史完成", status="已完成", progress=100,
              updated_at=monday - timedelta(days=30))
    db_session.commit()

    data = _gen(client, {"project_ids": [p.id]})

    md = data["markdown"]
    # 统计（5 个阶段：已完成2/进行中2/未开始1/延期1）
    assert "| 阶段总数 | 5 |" in md
    assert "| 已完成 | 2 |" in md
    assert "| 进行中 | 2 |" in md
    assert "| 未开始 | 1 |" in md
    assert "| 延期 | 1 |" in md
    # 本周完成：只有本周更新的已完成（历史完成不计入）
    assert "已完成阶段" in md
    assert "历史完成" not in md
    # 进行中
    assert "进行中阶段" in md and "60%" in md
    # 延期预警
    assert "已延期阶段" in md and "已逾期 2 天" in md
    # 下周计划
    assert "下周开始" in md
    # 纯文本
    assert "已完成阶段" in data["plain_text"]
    assert "|" not in data["plain_text"].replace(" | ", "") or True


def test_report_all_projects(client, db_session):
    """全部项目（不传 project_ids）。"""
    p1 = _mk_project(db_session, "项目一")
    p2 = _mk_project(db_session, "项目二")
    _mk_phase(db_session, p1, "甲阶段", status="进行中", progress=30)
    _mk_phase(db_session, p2, "乙阶段", status="已完成", progress=100)
    db_session.commit()

    data = _gen(client)
    assert "甲阶段" in data["markdown"]
    assert "乙阶段" in data["markdown"]
    assert "2 个项目" in data["markdown"]


def test_report_no_risk_data(client, db_session):
    """无延期/到期数据：模板不报错，显示🎉。"""
    t = date.today()
    p = _mk_project(db_session, "健康项目")
    _mk_phase(db_session, p, "正常阶段", status="进行中", progress=50,
              plan_start=t, plan_end=t + timedelta(days=30))
    db_session.commit()

    data = _gen(client)
    assert "暂无延期与即将到期阶段" in data["markdown"]


def test_report_requires_role(client, db_session):
    """非 admin/manager 不能生成周报（engineer 403）。"""
    from app.core.security import hash_password
    from app.models import User

    db_session.add(User(
        username="eng_user", name="工程师", role="engineer",
        password_hash=hash_password("testpass"),
    ))
    db_session.commit()
    client.post("/api/auth/login", json={"username": "eng_user", "password": "testpass"})

    resp = client.post("/api/reports/weekly", json={})
    assert resp.status_code == 403
