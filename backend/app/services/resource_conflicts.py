"""资源冲突检测（CONFLICT_MODEL_V2 v2 — 人员并行视角）。

同一资源被分配到多个阶段时，若阶段计划时间窗口**深度重叠**且该人员并行超限，
即为资源冲突。按资源（人员）聚合，每人独立判定并行数。

规则（CONFLICT_MODEL_V2 §2.1/§2.2，取代 PHASE6_DEV_PLAN.md T4 对应描述）：
1. 按 assignee 分组，取所有 assigned 阶段
2. P8 交付阶段不参与冲突对生成（决策 ①：f32717d 起三处全排除——甘特/热力图/冲突；
   P9 交付排除随 PHASE_TYPES_V2 实施——当前库无 P9 数据）
3. 重叠判定严格 `<`：max(start_a, start_b) < min(end_a, end_b)（背靠背不算）
4. 同项目的两个阶段不算冲突（正常分工，不算资源冲突）
5. plan_start/plan_end 任一为 null → 跳过
6. 状态为 已完成/搁置 → 跳过（阶段级；2026-09-03 阶段级「已搁置」同步改名为「搁置」）
   所属项目状态为 搁置 → 跳过（项目级，PROJECT_SHELVE §2.3；旧值兼容已移除）
7. 同一对阶段只报一次（i < j 遍历天然去重）
8. **重叠深度阈值**（项目并行是常态，仅"深度重叠"才报警）：
   - 重叠天数 ≥ _MIN_OVERLAP_DAYS（绝对下限，避免交接尾巴误报）
   - 且 重叠天数 ≥ 较短阶段工期的 _MIN_OVERLAP_RATIO（相对深度）
9. **人员并行视角**（决策 ②，与热力图 ⚠ 同口径）：该资源在重叠窗口内
   同时活跃阶段数 > _MAX_PARALLEL 才报警（活跃 = 计划窗口与重叠区间相交）
10. **手动消除**（§2.3，v2.1 阶段粒度）：conflict_override 已记录的
    (resource_id, phase_id) 阶段整体退出该资源检测（不参与对生成与并行计数；
    不影响其他资源对同一阶段的判定）
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConflictOverride, Resource
from app.schemas import ConflictPair, ResourceConflict

# 不参与冲突检测的状态（已结束/不活跃）
_SKIP_STATUSES = ("已完成", "搁置")
# 项目级搁置状态（PROJECT_SHELVE §2.3/决策 4；旧值「已搁置」兼容已移除——2026-08-28）
_SHELVED_PROJECT_STATUSES = ("搁置",)
# 不参与冲突检测的阶段类型（决策 ①：交付族三处全排除——甘特/热力图/冲突；PHASE_TYPES_V2 §四：
# 旧 P8 交付 + 新 P9 交付排除；新 P8=联调测试，机制上无法与旧 P8 区分，一并排除——用户知悉）
_SKIP_PHASE_TYPES = ("P8", "P9")
# 冲突判定阈值：重叠需足够"深"（方案 A，2026-08-25 用户确认）
_MIN_OVERLAP_DAYS = 10  # 绝对下限（天）：两周以上的整段重叠
_MIN_OVERLAP_RATIO = 0.6  # 重叠天数 ≥ 较短阶段工期的比例
# 并行上限：重叠窗口内该资源同时活跃的阶段数 ≤ 3 视为正常并行，不报冲突
_MAX_PARALLEL = 3


def _active_phases(resource: Resource) -> list:
    """该资源名下可参与冲突检测的阶段（类型非 P8、有完整日期、状态活跃、项目未搁置/非专项）。"""
    return [
        ph for ph in resource.phases
        if ph.phase_type not in _SKIP_PHASE_TYPES
        and ph.plan_start is not None and ph.plan_end is not None
        and ph.status not in _SKIP_STATUSES
        and not (ph.project is not None and ph.project.status in _SHELVED_PROJECT_STATUSES)
        # 专项项目：独立监控对象，不参与冲突检测（SPECIAL_PROJECT §二）
        and not (ph.project is not None and ph.project.is_special)
    ]


def _overlap_interval(a_start, a_end, b_start, b_end) -> tuple | None:
    """重叠区间 (start, end)；不重叠（含背靠背）返回 None。"""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start < end:
        return (start, end)
    return None


def _overlap_days(a_start, a_end, b_start, b_end) -> int | None:
    """重叠天数；不重叠（含背靠背）返回 None。"""
    interval = _overlap_interval(a_start, a_end, b_start, b_end)
    return (interval[1] - interval[0]).days if interval else None


def _parallel_count(phases: list, overlap_start, overlap_end) -> int:
    """重叠窗口内该资源**同时活跃**的峰值阶段数（含冲突双方）。

    用户 2026-08-28：相交计数会把"一前一后不同时存在"的阶段（如 478 8/5-8/21
    与 498 8/27-9/2）都算入 → 虚增并行。改为扫描线峰值（与热力图 peak_parallel
    同口径）：窗口内任意时刻同时活跃的最大阶段数 > _MAX_PARALLEL 才报冲突。
    """
    events: list[tuple[date, int]] = []
    for ph in phases:
        if ph.plan_start is None or ph.plan_end is None:
            continue
        if ph.plan_start < overlap_end and ph.plan_end > overlap_start:
            events.append((ph.plan_start, 1))
            events.append((ph.plan_end, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # 同日结束先于开始（背靠背交接日不算并行）
    peak = 0
    cur = 0
    for _d, delta in events:
        cur += delta
        if cur > peak:
            peak = cur
    return peak


def _is_deep_conflict(days: int, a_duration: int, b_duration: int) -> bool:
    """深度冲突判定：重叠绝对天数达标 且 覆盖较短阶段 60% 以上。

    一定的项目并行是正常状态，只有"两周以上的整段重叠"才值得标记。
    """
    if days < _MIN_OVERLAP_DAYS:
        return False
    shortest = min(a_duration, b_duration)
    return days * 10 >= shortest * 6  # days >= shortest * 0.6


def _overridden_phases(db: Session) -> dict[int, set[int]]:
    """被消除的阶段：{resource_id: set(phase_id)}（v2.1 按阶段语义——该阶段不计入该资源并行计算）。"""
    result: dict[int, set[int]] = {}
    for ov in db.scalars(select(ConflictOverride)):
        result.setdefault(ov.resource_id, set()).add(ov.phase_id)
    return result


def detect_conflicts(db: Session) -> list[ResourceConflict]:
    """检测全部资源冲突。

    返回按资源分组：每人一份 conflicts 列表（按重叠天数降序，最严重的在前）。
    每人的并行判定独立（人员并行视角，CONFLICT_MODEL_V2 §2.2）。
    """
    resources = db.scalars(select(Resource).order_by(Resource.id)).all()
    overridden_map = _overridden_phases(db)
    result: list[ResourceConflict] = []

    for res in resources:
        # 已消除的阶段（v2.1：该阶段不计入该资源并行计算——剔除后不参与对生成与并行计数）
        overridden = overridden_map.get(res.id, frozenset())
        phases = [ph for ph in _active_phases(res) if ph.id not in overridden]
        pairs: list[ConflictPair] = []
        for i in range(len(phases)):
            for j in range(i + 1, len(phases)):
                a, b = phases[i], phases[j]
                # 同项目两个阶段：正常分工，不算冲突
                if a.project_id == b.project_id:
                    continue
                days = _overlap_days(a.plan_start, a.plan_end, b.plan_start, b.plan_end)
                if days is None:
                    continue
                # 深度判定：重叠需足够深（并行是常态，仅整段重叠报警）
                a_duration = max((a.plan_end - a.plan_start).days, 1)
                b_duration = max((b.plan_end - b.plan_start).days, 1)
                if not _is_deep_conflict(days, a_duration, b_duration):
                    continue
                # 并行判定（人员视角）：重叠窗口内该资源活跃阶段 ≤ 3 视为正常并行，不报冲突
                interval = _overlap_interval(a.plan_start, a.plan_end, b.plan_start, b.plan_end)
                if _parallel_count(phases, interval[0], interval[1]) <= _MAX_PARALLEL:
                    continue
                pairs.append(ConflictPair(
                    phase_a_id=a.id,
                    phase_a_name=a.name,
                    project_a_id=a.project_id,
                    project_a_name=a.project.name,
                    phase_b_id=b.id,
                    phase_b_name=b.name,
                    project_b_id=b.project_id,
                    project_b_name=b.project.name,
                    overlap_days=days,
                    overlap_start=interval[0],
                    overlap_end=interval[1],
                ))
        if pairs:
            # 最严重的冲突在前
            pairs.sort(key=lambda p: (-p.overlap_days, p.phase_a_id, p.phase_b_id))
            result.append(ResourceConflict(
                resource_id=res.id,
                resource_name=res.name,
                conflicts=pairs,
            ))

    return result
