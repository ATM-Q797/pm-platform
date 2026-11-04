"""站内通知写入（二期①，用户 2026-11-04）。

只负责把一条通知挂进当前事务，不 commit——调用方在业务成功后统一提交，
于是「业务成功但通知丢失」不会发生（同一事务，要么都成要么都不成）。
通知写库失败会让整个业务操作回滚，这是刻意的：审批结果必须让申请人看得见，
静默丢掉通知等于把这次修复要解决的问题又留在了暗处。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, Project, User


def notify(db: Session, user_id: int, type: str, title: str,
           body: str | None = None, link: str | None = None) -> Notification:
    """给单个账号挂一条未读通知（不提交事务）。"""
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    db.add(n)
    return n


def project_owner_user_ids(db: Session, project: Project) -> list[int]:
    """项目负责人的账号 id 列表——与 is_project_owner 非 admin 口径同源。

    managed_by 命中即唯一负责人；为空（Excel 导入项目）时按 owner 文本找在职账号。
    同名账号都会收到（姓名回退口径系用户 2026-10-30 拍板，此处不另立规则）。
    """
    if project.managed_by is not None:
        return [project.managed_by]
    rows = db.scalars(
        select(User.id).where(User.name == project.owner, User.is_active.is_(True))
    ).all()
    return list(rows)
