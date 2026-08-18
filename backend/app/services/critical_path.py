"""关键路径计算（CPM - Critical Path Method）。

基于项目阶段依赖关系计算关键路径：
- 正向：拓扑排序 → 最早开始/结束（ES/EF）
- 反向：最晚开始/结束（LS/LF）
- 总时差（LS - ES）为 0 的阶段即为关键路径

规则与边界（见 docs/PHASE6_DEV_PLAN.md T1）：
- 依赖类型：第一版只精确处理 FS；SS/FF/SF 按 FS 近似（lag 忽略）
- 无日期阶段（plan_start/plan_end 任一为空）跳过，不参与计算
- 工期 = plan_end - plan_start，不足 1 天按 1 天
- 无依赖/并行阶段：仅工期最长的路径为关键路径（标准 CPM 定义，
  与 PHASE6_PLAN.md 的"无依赖项目所有阶段都是关键路径"表述不同——
  按标准 CPM 实现：存在浮动的阶段不算关键路径）
- 多终点：反向计算从所有终点的 LF = max(EF) 出发
- 循环依赖防御：Kahn 算法剩余节点按 id 兜底排序，不崩溃
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dependency, Phase, Project
from app.schemas import CriticalPathResult


def compute_critical_path(db: Session, project_id: int) -> CriticalPathResult | None:
    """计算项目的关键路径，返回关键阶段 id 列表、总工期（天）、路径阶段名。"""
    project = db.get(Project, project_id)
    if project is None:
        return None

    # 仅参与计算：有完整计划日期的阶段
    phases = [p for p in project.phases if p.plan_start is not None and p.plan_end is not None]
    if not phases:
        return CriticalPathResult(critical_phase_ids=[], total_duration=0, path=[])

    phase_ids = {p.id for p in phases}
    duration: dict[int, int] = {
        p.id: max((p.plan_end - p.plan_start).days, 1) for p in phases
    }

    # 依赖图（仅保留两端都参与计算的边）
    deps = db.execute(
        select(Dependency)
        .join(Phase, Dependency.from_phase_id == Phase.id)
        .where(Phase.project_id == project_id)
    ).scalars().all()
    preds: dict[int, list[int]] = {pid: [] for pid in phase_ids}
    succs: dict[int, list[int]] = {pid: [] for pid in phase_ids}
    for d in deps:
        if d.from_phase_id in phase_ids and d.to_phase_id in phase_ids:
            preds[d.to_phase_id].append(d.from_phase_id)
            succs[d.from_phase_id].append(d.to_phase_id)

    # ---------- 拓扑排序（Kahn，按 id 保持确定性顺序） ----------
    indeg = {pid: len(preds[pid]) for pid in phase_ids}
    queue = [pid for pid in sorted(phase_ids) if indeg[pid] == 0]
    order: list[int] = []
    while queue:
        pid = queue.pop(0)
        order.append(pid)
        for s in sorted(succs[pid]):
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    # 环防御：未入序的节点按 id 兜底
    if len(order) < len(phase_ids):
        order.extend(pid for pid in sorted(phase_ids) if pid not in order)

    # ---------- 正向：最早开始/结束 ----------
    es = {pid: 0 for pid in phase_ids}
    ef = {pid: duration[pid] for pid in phase_ids}
    for pid in order:
        for p in preds[pid]:
            es[pid] = max(es[pid], ef[p])
        ef[pid] = es[pid] + duration[pid]

    total_duration = max(ef.values())

    # ---------- 反向：最晚开始/结束 ----------
    lf = {pid: total_duration for pid in phase_ids}
    ls = {pid: total_duration - duration[pid] for pid in phase_ids}
    for pid in reversed(order):
        for s in succs[pid]:
            lf[pid] = min(lf[pid], ls[s])
        ls[pid] = lf[pid] - duration[pid]

    # ---------- 关键路径：总时差 = 0 ----------
    critical_phase_ids = sorted(pid for pid in phase_ids if ls[pid] == es[pid])

    name_map = {p.id: p.name for p in phases}
    path = [name_map[pid] for pid in sorted(critical_phase_ids, key=lambda pid: (es[pid], pid))]

    return CriticalPathResult(
        critical_phase_ids=critical_phase_ids,
        total_duration=total_duration,
        path=path,
    )
