"""ORM 模型汇总。

导入所有模型类，使 SQLAlchemy 在 Base.metadata 中注册全部表。
创建/初始化数据库前必须先导入本模块。
"""
from app.models.resource import Resource
from app.models.template import Template, TemplateDependency, TemplatePhase
from app.models.project import Project
from app.models.phase import Phase, ReworkLog, phase_assignee
from app.models.dependency import Dependency

__all__ = [
    "Resource",
    "Template",
    "TemplatePhase",
    "TemplateDependency",
    "Project",
    "Phase",
    "ReworkLog",
    "phase_assignee",
    "Dependency",
]
