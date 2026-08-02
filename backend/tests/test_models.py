"""ORM 模型层测试：建表、约束、级联删除。"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Dependency, Phase, Project, Resource, Template, TemplatePhase


def test_create_project_and_phase(db_session):
    project = Project(code="T-1", category="招标", name="测试项目", owner="张三", market="国内")
    db_session.add(project)
    db_session.commit()
    phase = Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1)
    db_session.add(phase)
    db_session.commit()
    assert phase.id is not None
    assert phase.status == "未开始"
    assert phase.progress == 0


def test_project_code_unique(db_session):
    db_session.add(Project(code="DUP", category="招标", name="A", owner="x", market="国内"))
    db_session.commit()
    db_session.add(Project(code="DUP", category="招标", name="B", owner="x", market="国内"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_resource_name_unique(db_session):
    db_session.add(Resource(name="曹俊杰"))
    db_session.commit()
    db_session.add(Resource(name="曹俊杰"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cascade_delete_project_to_phase(db_session):
    project = Project(code="C-1", category="招标", name="C", owner="x", market="国内")
    db_session.add(project)
    db_session.flush()
    db_session.add(Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1))
    db_session.commit()
    assert db_session.query(Phase).count() == 1
    db_session.delete(project)
    db_session.commit()
    assert db_session.query(Phase).count() == 0


def test_template_phase_unique_constraint(db_session):
    tpl = Template(name="测试模板", category="招标研发")
    db_session.add(tpl)
    db_session.flush()
    db_session.add(TemplatePhase(template_id=tpl.id, phase_type="P1", name="需求评估", sequence=1))
    db_session.commit()
    # 同 template_id + sequence 重复 → 违反约束
    db_session.add(TemplatePhase(template_id=tpl.id, phase_type="P2", name="配置评估", sequence=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_dependency_unique(db_session):
    project = Project(code="DU-1", category="招标", name="DU", owner="x", market="国内")
    db_session.add(project)
    db_session.flush()
    p1 = Phase(project_id=project.id, phase_type="P1", name="需求评估", sequence=1)
    p2 = Phase(project_id=project.id, phase_type="P4", name="工业设计", sequence=2)
    db_session.add_all([p1, p2])
    db_session.flush()
    db_session.add(Dependency(from_phase_id=p1.id, to_phase_id=p2.id))
    db_session.commit()
    db_session.add(Dependency(from_phase_id=p1.id, to_phase_id=p2.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
