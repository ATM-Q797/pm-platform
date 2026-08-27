"""资源冲突检测。

同一资源被分配到多个阶段时，若阶段计划时间窗口**深度重叠**，即为资源冲突。

规则（见 docs/PHASE6_DEV_PLAN.md T4，2026-08-25 优化）：
1. 按 assignee 分组，取所有 assigned 阶段
2. 重叠判定严格 `<`：max(start_a, start_b) < min(end_a, end_b)（背靠背不算）
3. 同项目的两个阶段不算冲突（正常分工，不算资源冲突）
4. plan_start/plan_end 任一为 null → 跳过
5. 状态为 已完成/已搁置 → 跳过（阶段级）
   所属项目状态为 搁置/已搁置 → 跳过（项目级，PROJECT_SHELVE §2.3）
6. 同一对阶段只报一次（i < j 遍历天然去重）
7. **重叠深度阈值**（项目并行是常态，仅"深度重叠"才报警）：
   - 重叠天数 ≥ _MIN_OVERLAP_DAYS（绝对下限，避免交接尾巴误报）
   - 且 重叠天数 ≥ 较短阶段工期的 _MIN_OVERLAP_RATIO（相对深度）
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resource
from app.schemas import ConflictPair, ResourceConflict

# 不参与冲突检测的状态（已结束/不活跃）
_SKIP_STATUSES = ("已完成", "已搁置")
# 项目级搁置状态（双 key：新值「搁置」+ 旧值「已搁置」，PROJECT_SHELVE §2.3/决策 4）：
# 搁置项目不占资源，其阶段退出冲突检测
_SHELVED_PROJECT_STATUSES = ("搁置", "已搁置")
# 冲突判定阈值：重叠需足够"深"（方案 A，2026-08-25 用户确认）
_MIN_OVERLAP_DAYS = 10  # 绝对下限（天）：两周以上的整段重叠
_MIN_OVERLAP_RATIO = 0.6  # 重叠天数 ≥ 较短阶段工期的比例
# 并行上限：重叠窗口内该资源同时活跃的阶段数 ≤ 3 视为正常并行，不报冲突
_MAX_PARALLEL = 3


def _active_phases(resource: Resource) -> list:
    """该资源名下可参与冲突检测的阶段（有完整日期、状态活跃、项目未搁置）。"""
    return [
        ph for ph in resource.phases
        if ph.plan_start is not None and ph.plan_end is not None
        and ph.status not in _SKIP_STATUSES
        and not (ph.project is not None and ph.project.status in _SHELVED_PROJECT_STATUSES)
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
    """重叠窗口内该资源同时活跃的阶段总数（含冲突双方）。

    活跃 = 计划窗口与重叠区间有交集（plan_start < overlap_end 且 plan_end > overlap_start）。
    """
    return sum(
        1 for ph in phases
        if ph.plan_start is not None and ph.plan_end is not None
        and ph.plan_start < overlap_end and ph.plan_end > overlap_start
    )


def _is_deep_conflict(days: int, a_duration: int, b_duration: int) -> bool:
    """深度冲突判定：重叠绝对天数达标 且 覆盖较短阶段 60% 以上。

    一定的项目并行是正常状态，只有"两周以上的整段重叠"才值得标记。
    """
    if days < _MIN_OVERLAP_DAYS:
        return False
    shortest = min(a_duration, b_duration)
    return days * 10 >= shortest * 6  # days >= shortest * 0.6


def detect_conflicts(db: Session) -> list[ResourceConflict]:
    """检测全部资源冲突。

    返回按资源分组：每人一份 conflicts 列表（按重叠天数降序，最严重的在前）。
    """
    resources = db.scalars(select(Resource).order_by(Resource.id)).all()
    result: list[ResourceConflict] = []

    for res in resources:
        phases = _active_phases(res)
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
                # 并行判定：重叠窗口内活跃阶段 ≤ 3 视为正常并行，不报冲突
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
