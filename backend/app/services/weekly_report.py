"""周报生成（T7）。

按指定项目（或全部）聚合当前数据，Jinja2 渲染 Markdown 周报。

内容：
1. 📊 整体进度概览：阶段总数 / 已完成 / 进行中 / 未开始 / 延期 + 完成率
2. ⚠️ 风险预警：延期阶段（plan_end < 今天 && 未完成）+ 即将到期（7 天内）
3. ✅ 本周完成：status == 已完成 且 updated_at 在本周内（近似：本周有更新的已完成阶段）
4. 🔄 进行中：status == 进行中（含进度 %）
5. 📅 下周计划：status == 未开始 且 plan_start 在下周

日期语义（周一为一周起点）：
- 本周 = [本周一, 下周一)
- 下周 = [下周一, 下下周一)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from jinja2 import Environment
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Phase, Project

# 延期/到期判定：活跃状态（未完成、未搁置）
_ACTIVE_STATUSES = ("未开始", "进行中")
# 即将到期窗口（天）
_DUE_SOON_DAYS = 7

_TEMPLATE = """# 📋 项目管理周报

> 生成时间：{{ generated_at }}{% if scope %}　|　范围：{{ scope }}{% endif %}

## 📊 整体进度概览

| 指标 | 数值 |
|------|------|
| 阶段总数 | {{ total_phases }} |
| 已完成 | {{ done_count }} |
| 进行中 | {{ active_count }} |
| 未开始 | {{ pending_count }} |
| 延期 | {{ delayed_count }} |
| **完成率** | **{{ done_rate }}%** |

{% if risk_phases %}
## ⚠️ 风险预警

{% if overdue_phases %}
### 已延期（{{ overdue_phases|length }}）

{% for p in overdue_phases %}- **{{ p.project_name }}** · {{ p.phase_name }} — 已逾期 {{ p.overdue_days }} 天
{% endfor %}
{% endif %}
{% if due_soon_phases %}
### 即将到期（{{ due_soon_phases|length }}，7 天内）

{% for p in due_soon_phases %}- **{{ p.project_name }}** · {{ p.phase_name }} — 剩 {{ p.days_left }} 天
{% endfor %}
{% endif %}
{% else %}
## ⚠️ 风险预警

🎉 暂无延期与即将到期阶段。
{% endif %}

{% if done_phases %}
## ✅ 本周完成（{{ done_phases|length }}）

{% for p in done_phases %}- **{{ p.project_name }}** · {{ p.phase_name }}
{% endfor %}
{% else %}
## ✅ 本周完成

（本周暂无完成阶段）
{% endif %}

{% if active_phases %}
## 🔄 进行中（{{ active_phases|length }}）

{% for p in active_phases %}- **{{ p.project_name }}** · {{ p.phase_name }} — 进度 {{ p.progress }}%
{% endfor %}
{% else %}
## 🔄 进行中

（当前无进行中阶段）
{% endif %}

{% if next_week_phases %}
## 📅 下周计划（{{ next_week_phases|length }}）

{% for p in next_week_phases %}- **{{ p.project_name }}** · {{ p.phase_name }}{% if p.plan_start %}（计划 {{ p.plan_start }} 开始）{% endif %}
{% endfor %}
{% else %}
## 📅 下周计划

（下周暂无计划开始阶段）
{% endif %}
"""


def _monday(d: date) -> date:
    """本周一（周一为一周起点）。"""
    return d - timedelta(days=d.weekday())


def build_weekly_report(
    db: Session, project_ids: list[int] | None = None
) -> dict:
    """生成周报，返回 { markdown, plain_text, generated_at }。"""
    today = date.today()
    week_start = _monday(today)
    week_end = week_start + timedelta(days=7)
    next_week_start = week_end
    next_week_end = next_week_start + timedelta(days=7)

    # 范围与阶段收集
    stmt = select(Project).order_by(Project.id)
    if project_ids:
        stmt = stmt.where(Project.id.in_(project_ids))
    projects = list(db.scalars(stmt))
    phases = [ph for p in projects for ph in p.phases]

    scope = f"{len(projects)} 个项目" if not project_ids else f"{len(projects)} 个项目（指定）"

    # ---------- 状态统计 ----------
    done_count = sum(1 for ph in phases if ph.status == "已完成")
    active_count = sum(1 for ph in phases if ph.status == "进行中")
    pending_count = sum(1 for ph in phases if ph.status == "未开始")
    # 计算式延期：plan_end < 今天 && 状态活跃
    delayed_count = sum(
        1 for ph in phases
        if ph.plan_end is not None and ph.plan_end < today and ph.status in _ACTIVE_STATUSES
    )
    total_phases = len(phases)
    done_rate = round(done_count / total_phases * 100) if total_phases else 0

    # ---------- 风险预警 ----------
    overdue_phases = sorted(
        [
            {
                "project_name": ph.project.name,
                "phase_name": ph.name,
                "overdue_days": (today - ph.plan_end).days,
            }
            for ph in phases
            if ph.plan_end is not None and ph.plan_end < today and ph.status in _ACTIVE_STATUSES
        ],
        key=lambda x: -x["overdue_days"],
    )
    due_soon_phases = sorted(
        [
            {
                "project_name": ph.project.name,
                "phase_name": ph.name,
                "days_left": (ph.plan_end - today).days,
            }
            for ph in phases
            if ph.plan_end is not None
            and today <= ph.plan_end <= today + timedelta(days=_DUE_SOON_DAYS)
            and ph.status in _ACTIVE_STATUSES
        ],
        key=lambda x: x["days_left"],
    )
    risk_phases = bool(overdue_phases or due_soon_phases)

    # ---------- 本周完成（updated_at 在本周内的已完成阶段） ----------
    done_phases = [
        {
            "project_name": ph.project.name,
            "phase_name": ph.name,
        }
        for ph in phases
        if ph.status == "已完成"
        and ph.updated_at is not None
        and week_start <= _as_date(ph.updated_at) < week_end
    ]

    # ---------- 进行中 ----------
    active_phases = sorted(
        [
            {
                "project_name": ph.project.name,
                "phase_name": ph.name,
                "progress": ph.progress,
            }
            for ph in phases
            if ph.status == "进行中"
        ],
        key=lambda x: -x["progress"],
    )

    # ---------- 下周计划 ----------
    next_week_phases = sorted(
        [
            {
                "project_name": ph.project.name,
                "phase_name": ph.name,
                "plan_start": ph.plan_start.isoformat() if ph.plan_start else None,
            }
            for ph in phases
            if ph.status == "未开始"
            and ph.plan_start is not None
            and next_week_start <= ph.plan_start < next_week_end
        ],
        key=lambda x: x["plan_start"] or "",
    )

    # ---------- 渲染 ----------
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    template = env.from_string(_TEMPLATE)
    markdown = template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        scope=scope,
        total_phases=total_phases,
        done_count=done_count,
        active_count=active_count,
        pending_count=pending_count,
        delayed_count=delayed_count,
        done_rate=done_rate,
        risk_phases=risk_phases,
        overdue_phases=overdue_phases,
        due_soon_phases=due_soon_phases,
        done_phases=done_phases,
        active_phases=active_phases,
        next_week_phases=next_week_phases,
    ).strip()

    return {
        "markdown": markdown,
        "plain_text": _markdown_to_text(markdown),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _as_date(dt: datetime) -> date:
    """datetime → date（SQLite 可能返回 date 类型）。"""
    return dt.date() if isinstance(dt, datetime) else dt


def _markdown_to_text(md: str) -> str:
    """Markdown 降级为纯文本（去标记符，保留可读性）。"""
    lines = []
    for line in md.splitlines():
        line = line.rstrip()
        if line.startswith("|") and set(line) <= {"|", "-", ":", " ", ""}:
            continue  # 表头分隔行
        if line.startswith("|"):
            # 表格行：去掉管道与对齐
            cells = [c.strip() for c in line.strip("|").split("|")]
            lines.append(" | ".join(cells))
            continue
        stripped = line.lstrip("#>").strip()
        if not stripped:
            lines.append("")
            continue
        # 列表项去 '- '、'**'、链接语法
        if stripped.startswith("- "):
            stripped = stripped[2:]
        lines.append(stripped.replace("**", "").replace("`", ""))
    # 压缩连续空行
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()
