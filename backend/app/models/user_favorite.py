"""user_favorite（用户关注项目）模型。

关注是用户级行为：每个用户独立维护关注列表。
- 关注的项目在项目列表中置顶（排序优先级高于 id）
- 项目/用户删除时级联清理
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserFavorite(Base):
    __tablename__ = "user_favorite"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
