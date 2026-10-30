"""项目编号生成——全平台单一来源（用户 2026-10-30 规则）。

- **普通项目**：纯数字序列，取非专项项目最大编号 + 1；逐个跳过已被任何项目占用的值
  （历史专项可能占用过普通号段内的数字，跳过可避免 `project.code` 唯一约束冲突）。
- **专项项目**：独立 ZX 系列（ZX001 起），**不进入普通数字序列**——专项单独核算、
  不占用项目编号。

调用方：routers/projects.py（创建）、services/excel_importer.py（全量替换/专项/合并导入）、
services/report_service.py（编号预览）。三处同源，避免口径漂移。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project

# 纯数字编号正则（普通项目）
CODE_INT_RE = re.compile(r"^\d+$")
# 专项 ZX 编号正则（ZX001 / zx1 等大小写混写均识别）
_SPECIAL_CODE_RE = re.compile(r"^ZX(\d+)$", re.IGNORECASE)


def taken_codes(db: Session) -> set[str]:
    """当前全部项目编号（任何类型），供取号时跳过占用值。"""
    return set(db.scalars(select(Project.code)).all())


def _normal_numeric_codes(db: Session) -> list[int]:
    """非专项项目的纯数字编号值。"""
    codes = db.scalars(
        select(Project.code).where(Project.is_special.is_(False))
    ).all()
    return [int(c) for c in codes if c and CODE_INT_RE.match(c)]


def next_project_codes(db: Session, count: int) -> list[str]:
    """批量生成 count 个连续普通项目编号，逐项跳过已被任何项目占用的值。

    批量版一次性取快照：既避免「只保护首号」的撞号（历史专项占用普通号段内的编号值），
    也把 n 次单号查询收敛为一次扫描。
    """
    if count <= 0:
        return []
    nums = _normal_numeric_codes(db)
    candidate = max(nums) + 1 if nums else 1
    taken = taken_codes(db)
    out: list[str] = []
    while len(out) < count:
        code = str(candidate)
        if code not in taken:
            out.append(code)
        candidate += 1
    return out


def next_project_code(db: Session) -> str:
    """下一个普通项目编号（数字序列）。"""
    return next_project_codes(db, 1)[0]


def next_special_codes(db: Session, count: int) -> list[str]:
    """批量生成 count 个连续专项项目编号（ZX 独立序列，ZX001 起）。"""
    if count <= 0:
        return []
    codes = db.scalars(select(Project.code).where(Project.is_special.is_(True))).all()
    nums = [
        int(m.group(1))
        for c in codes
        if c and (m := _SPECIAL_CODE_RE.match(c))
    ]
    candidate = max(nums) + 1 if nums else 1
    taken = taken_codes(db)
    out: list[str] = []
    while len(out) < count:
        code = f"ZX{candidate:03d}"
        if code not in taken:
            out.append(code)
        candidate += 1
    return out


def next_special_code(db: Session) -> str:
    """下一个专项项目编号（ZX 独立序列）。"""
    return next_special_codes(db, 1)[0]
