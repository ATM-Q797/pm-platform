"""项目健康度（8-2）——规则灯评级：事实触发档位，三处消费的口径唯一来源。

看板 / 列表 / 详情调用同一函数。2026-11-06 用户裁定（再论证）：废除五维加权分，
改为规则灯——只认事实，事实直接触发档位，一行短语即懂，当场可对照项目数据核验
（一目了然：无分数、无小数、无分母、无公式）。

| 事实 | 触发 | 档位 | 短语 |
|---|---|---|---|
| 阶段逾期 ≥7 天未完成 | 有 1 个即触发 | red | 1个阶段逾期X天 / N个阶段逾期最长X天 |
| 阶段逾期 1–6 天 | 有 1 个即触发 | yellow | 同上 |
| 资源冲突 ≥3 对（阶段对去重） | 达 3 对触发 | yellow | 资源冲突N对 |
| 无阶段 / 活跃阶段均无计划日期 | 无法判定 | gray | 未评估（detail 按成因分句） |
| 有事实 + 部分活跃阶段无计划日期 | 事实定档 | 按事实 | facts 附注「N 个活跃阶段无计划日期，未纳入判定」 |
| 无事实 + 存在无计划日期的活跃阶段 | 无法判定全貌 | gray | 未评估（不冒充正常） |
| 以上均无（含全部阶段已完成的项目） | — | green | 正常 |

档位规则：有红事实 → red；否则有黄事实 → yellow；无法判定 → gray；否则 green。
多事实同现 reason 取最严重一条短语（红 > 黄；同档逾期 > 冲突）。
短语 N = 全部逾期阶段数（含 1–6 天档），X = 最长逾期天数；
事实只来自有日期的活跃阶段（状态 ∉ {已完成, 搁置}），完成阶段不产生逾期也不计冲突。

口径复用（跨端一致）：
- 逾期 = 阶段 plan_end < 今天且状态 ∉ {已完成, 搁置}（与看板「延期项目」同源）；
- 冲突 = resource_conflicts.detect_conflicts，按 (phase_a_id, phase_b_id) 对去重
  （与 8-1 风险队列 conflict 行同源）。

搁置项目不评（调用方短路，显示「—」）；专项项目在调用方查询层排除（与看板/快照同口径）。
"""
from __future__ import annotations

from datetime import date

from app.models import Phase, Project
from app.schemas import HealthFact, HealthStatus, ResourceConflict

# 阈值（2026-11-06 用户裁定）：逾期 ≥7 天 = 红（与「即将到期 7 天」窗口对称）；
# 冲突 ≥3 对才亮（1–2 对属资源常态占用，不预警）
_OVERDUE_RED_DAYS = 7
_CONFLICT_WARN_PAIRS = 3

# 逾期判定排除的状态（与看板 delayed_phases 同源）
_DONE_STATUSES = ("已完成", "搁置")


def _delay_fact(phases: list[Phase], today: date) -> tuple[HealthFact | None, int]:
    """阶段逾期事实（明细带阶段名与日期，取最长逾期定档）→ (fact, 最长逾期天数)。"""
    overdue = [ph for ph in phases
               if ph.plan_end is not None and ph.plan_end < today
               and ph.status not in _DONE_STATUSES]
    if not overdue:
        return None, 0
    by_days = sorted(overdue, key=lambda ph: (today - ph.plan_end).days, reverse=True)
    longest = (today - by_days[0].plan_end).days
    parts = [
        f"阶段「{ph.name}」逾期 {(today - ph.plan_end).days} 天（plan_end {ph.plan_end.isoformat()}）"
        for ph in by_days[:3]
    ]
    if len(overdue) > 3:
        parts.append(f"等共 {len(overdue)} 个逾期阶段")
    if len(overdue) == 1:
        phrase = f"1个阶段逾期{longest}天"
    else:
        phrase = f"{len(overdue)}个阶段逾期最长{longest}天"
    severity = 2 if longest >= _OVERDUE_RED_DAYS else 1
    return HealthFact(kind="delay", phrase=phrase, detail="；".join(parts), severity=severity), longest


def _conflict_fact(conflicts: list[ResourceConflict], project_id: int,
                   active_ids: set[int]) -> HealthFact | None:
    """资源冲突事实：涉该项目冲突对按阶段对去重，≥3 对才亮（黄）。

    完成/搁置阶段不计冲突——本层按活跃阶段 id 独立过滤（与 detect_conflicts
    上游排除同口径，双保险：防合成/缓存输入把完成阶段的旧冲突算进评级）。
    """
    seen: set[tuple[int, int]] = set()
    resources: list[str] = []
    for rc in conflicts:
        hit = False
        for p in rc.conflicts:
            mine = []
            if project_id == p.project_a_id:
                mine.append(p.phase_a_id)
            if project_id == p.project_b_id:
                mine.append(p.phase_b_id)
            if mine and all(pid in active_ids for pid in mine):
                seen.add(tuple(sorted((p.phase_a_id, p.phase_b_id))))
                hit = True
        if hit and rc.resource_name not in resources:
            resources.append(rc.resource_name)
    count = len(seen)
    if count < _CONFLICT_WARN_PAIRS:
        return None
    return HealthFact(
        kind="conflict",
        phrase=f"资源冲突{count}对",
        detail=f"资源冲突 {count} 对（涉及资源：{'、'.join(resources)}）",
        severity=1,
    )


def assess_health(
    project: Project,
    phases: list[Phase],
    conflicts: list[ResourceConflict],
    today: date,
) -> HealthStatus:
    """单项目规则灯评级（事实 → 档位；reason = 最严重事实短语）。

    conflicts = detect_conflicts(db) 结果（调用方一次检测、全项目复用）。
    规则边界（评审 #2 #3）：事实只来自有日期的活跃阶段；
    无事实但存在无计划日期的活跃阶段 → gray（未判定不冒充正常）；
    全部阶段完成/搁置或无阶段日期覆盖完整 → 按事实/绿。
    """
    if not phases:
        fact = HealthFact(kind="nodata", phrase="未评估",
                          detail="无阶段，无法判定风险", severity=0)
        return HealthStatus(band="gray", reason=fact.phrase, facts=[fact])
    active = [ph for ph in phases if ph.status not in _DONE_STATUSES]
    dated = [ph for ph in active if ph.plan_end is not None]
    undated = [ph for ph in active if ph.plan_end is None]
    if active and not dated:
        fact = HealthFact(kind="nodata", phrase="未评估",
                          detail="活跃阶段均无计划日期，无法判定风险", severity=0)
        return HealthStatus(band="gray", reason=fact.phrase, facts=[fact])
    delay_fact, _ = _delay_fact(phases, today)
    conflict_fact = _conflict_fact(conflicts, project.id, {ph.id for ph in active})
    facts = [f for f in (delay_fact, conflict_fact) if f is not None]
    if undated:
        facts.append(HealthFact(
            kind="nodata", phrase="",
            detail=f"{len(undated)} 个活跃阶段无计划日期，未纳入判定", severity=0))
    if not delay_fact and not conflict_fact:
        # 无事实：判定覆盖不完整 → 灰（不冒充正常）；覆盖完整（或全部阶段已完成）→ 绿
        if undated:
            fact = HealthFact(kind="nodata", phrase="未评估",
                              detail=f"{len(undated)} 个活跃阶段无计划日期，无法判定全貌", severity=0)
            return HealthStatus(band="gray", reason=fact.phrase, facts=[fact])
        fact = HealthFact(kind="clear", phrase="正常",
                          detail="无逾期阶段、无高密度资源冲突", severity=0)
        return HealthStatus(band="green", reason=fact.phrase, facts=[fact])
    facts.sort(key=lambda f: -f.severity)  # 稳定排序：同档时逾期在前（先入列表）
    band = "red" if facts[0].severity == 2 else "yellow"
    return HealthStatus(band=band, reason=facts[0].phrase, facts=facts)


def longest_overdue_days(phases: list[Phase], today: date) -> int:
    """该项目最长逾期天数（风险行排序键；无逾期 0）。"""
    days = [(today - ph.plan_end).days for ph in phases
            if ph.plan_end is not None and ph.plan_end < today
            and ph.status not in _DONE_STATUSES]
    return max(days, default=0)


def assess_projects(
    projects: list[Project],
    conflicts: list[ResourceConflict],
    today: date,
) -> dict[int, HealthStatus]:
    """批量评级：一次冲突检测全项目复用，返回 {project_id: HealthStatus}。

    - 搁置项目不评（不在返回 dict 中，调用方显示「—」）；
    - 专项项目由调用方的查询过滤（与看板同口径），本函数不再重复判断；
    - phases 经 project.phases 关系加载（selectin，批查询无 N+1）。
    """
    return {
        p.id: assess_health(p, list(p.phases), conflicts, today)
        for p in projects
        if p.status != "搁置"
    }
