"""资源/人员 API 路由，含负载查询。

对应 PROJECT_SPEC §4.2 资源/人员端点。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import ConflictOverride, Phase, Project, Resource, User
from app.schemas import (
    ConflictOverrideCreate,
    ConflictOverrideRead,
    ResourceConflict,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    ResourceWorkload,
)
from app.services.resource_conflicts import detect_conflicts
from app.services.resource_heatmap import (
    _SHELVED_PROJECT_STATUSES,
    build_heatmap,
)

router = APIRouter(prefix="/api/resources", tags=["资源/人员"])


@router.get("/conflicts", response_model=list[ResourceConflict])
def get_conflicts(db: Session = Depends(get_db)):
    """资源冲突检测：同一资源在重叠时间段被分配到不同项目的阶段。

    规则：严格重叠（背靠背不算）、同项目不算、缺日期/已完成/已搁置跳过、
    P8 交付不参与、并行 ≤3 不报、已 override 的资源×阶段对排除
    （CONFLICT_MODEL_V2 v2）。返回按资源分组，冲突对按重叠天数降序。
    """
    return detect_conflicts(db)


# ---------- 冲突手动消除（CONFLICT_MODEL_V2 §2.3） ----------


def _check_override_permission(user: User, phases: list[Phase], db: Session) -> None:
    """override 写权限（决策 1）：admin 全部；manager 仅自己负责项目
    涉及的资源×阶段对（两个阶段所属项目之一由其负责即可，与项目编辑权限一致：
    managed_by == user.id 或 managed_by 为空时 owner 文本匹配）；其他角色 403。
    """
    if user.role == "admin":
        return
    if user.role != "manager":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员或项目经理可消除冲突")

    def _managed(project: Project | None) -> bool:
        if project is None:
            return False
        return project.managed_by == user.id or (
            project.managed_by is None and project.owner == user.name
        )

    if not any(_managed(db.get(Project, ph.project_id)) for ph in phases):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能消除自己负责项目涉及的冲突")


@router.post(
    "/conflicts/{resource_id}/override",
    response_model=ConflictOverrideRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conflict_override(
    resource_id: int,
    payload: ConflictOverrideCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动消除某资源的某阶段（v2.1 按阶段语义：该阶段不计入该资源并行计算）。

    错误语义：重复消除同阶段 → 409；该阶段当前不冲突/不属于该资源 → 400；
    resource/phase id 不存在 → 404；权限不足 → 403；缺 reason → 422（Pydantic）。
    """
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, f"人员不存在: {resource_id}")

    ph = db.get(Phase, payload.phase_id)
    if ph is None:
        raise HTTPException(404, f"阶段不存在: {payload.phase_id}")
    # 阶段必须属于该资源（v2.1 粒度校验）
    if ph not in resource.phases:
        raise HTTPException(400, "该阶段不属于该人员，无法消除")

    _check_override_permission(user, [ph], db)

    # 重复消除 → 409
    dup = db.scalars(
        select(ConflictOverride).where(
            ConflictOverride.resource_id == resource_id,
            ConflictOverride.phase_id == payload.phase_id,
        )
    ).first()
    if dup is not None:
        raise HTTPException(409, "该阶段已消除，请勿重复操作")

    # 当前不构成冲突 → 400（阶段必须出现在该资源检测剩余对的成员中）
    current_phase_ids = {
        pid
        for rc in detect_conflicts(db) if rc.resource_id == resource_id
        for p in rc.conflicts
        for pid in (p.phase_a_id, p.phase_b_id)
    }
    if payload.phase_id not in current_phase_ids:
        raise HTTPException(400, "该阶段当前对该人员不构成冲突，无需消除")

    override = ConflictOverride(
        resource_id=resource_id,
        phase_id=payload.phase_id,
        reason=payload.reason,
        created_by=user.id,
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    return override


@router.get("/conflicts/overrides", response_model=list[ConflictOverrideRead])
def list_conflict_overrides(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全部消除记录（仅 admin/manager 可见，决策 3；防滥用）。"""
    if user.role not in ("admin", "manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员或项目经理可查看消除记录")
    return list(
        db.scalars(select(ConflictOverride).order_by(ConflictOverride.id.desc()))
    )


@router.delete("/conflicts/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conflict_override(
    override_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """撤销消除（恢复冲突报告）。权限与 POST 相同；不存在 → 404。"""
    override = db.get(ConflictOverride, override_id)
    if override is None:
        raise HTTPException(404, f"消除记录不存在: {override_id}")

    phases = [ph for ph in (db.get(Phase, override.phase_id),) if ph]
    _check_override_permission(user, phases, db)

    db.delete(override)
    db.commit()


def _phase_to_workload(ph: Phase) -> dict:
    """把阶段转为 workload dict（get_workload / get_all_workloads 共用）。"""
    return {
        "project_id": ph.project_id,
        "project_name": ph.project.name,
        "project_owner": ph.project.owner,  # 项目负责人
        "phase_id": ph.id,
        "phase_name": ph.name,
        "plan_start": ph.plan_start.isoformat() if ph.plan_start else None,
        "plan_end": ph.plan_end.isoformat() if ph.plan_end else None,
        "status": ph.status,
        "period": [
            ph.plan_start.isoformat() if ph.plan_start else None,
            ph.plan_end.isoformat() if ph.plan_end else None,
        ],
        "remark": ph.remark,  # 甘特悬浮显示备注（SPECIAL_PROJECT §五）
    }


def _workload_visible(ph: Phase) -> bool:
    """负载视图可见性（PROJECT_SHELVE §2.5 + 用户 2026-08-28：P8 交付不显示）。

    搁置项目的阶段不占资源负载；专项项目独立监控、不占资源负载（SPECIAL_PROJECT §二）；
    P8 交付占空间且不计入负载，资源负载视图无存在必要（甘特/热力图/冲突检测三处口径统一排除）。
    阶段级已完成/已搁置跳过逻辑沿用 resource_conflicts._SKIP_STATUSES 口径。
    """
    if ph.status in ("已完成", "已搁置"):
        return False
    if ph.project is not None and ph.project.status in _SHELVED_PROJECT_STATUSES:
        return False
    # 专项项目：资源负载不显示/不计入（SPECIAL_PROJECT §二）
    if ph.project is not None and ph.project.is_special:
        return False
    # P8/P9 交付族：资源负载不显示/不计入（用户 2026-08-28；PHASE_TYPES_V2 §四双兼容）
    if (ph.phase_type or "").upper() in ("P8", "P9"):
        return False
    return True


@router.get("", response_model=list[ResourceRead])
@router.get("/", response_model=list[ResourceRead], include_in_schema=False)
def list_resources(db: Session = Depends(get_db)):
    return list(db.scalars(select(Resource).order_by(Resource.id)))


@router.get("/all/workload", response_model=list[ResourceWorkload])
def get_all_workloads(db: Session = Depends(get_db)):
    """全员负载概览：一次返回所有人员的负载数据。

    用于资源负载视图（每人一行甘特图），避免前端发 N 个请求。
    按人员 id 升序，每人的阶段按 plan_start 升序。
    搁置项目（PROJECT_SHELVE §2.5）与已完成/已搁置阶段不占负载。
    注意：此静态路径必须注册在 /{resource_id}/workload 之前。
    """
    resources = list(db.scalars(select(Resource).order_by(Resource.id)))
    result: list[ResourceWorkload] = []
    for res in resources:
        # 可见阶段按 plan_start 排序（None 排最后）
        phases = sorted(
            (ph for ph in res.phases if _workload_visible(ph)),
            key=lambda ph: (ph.plan_start is None, ph.plan_start or date.min),
        )
        result.append(ResourceWorkload(
            resource={"id": res.id, "name": res.name, "role": res.role},
            workloads=[_phase_to_workload(ph) for ph in phases],
        ))
    return result


@router.get("/heatmap")
def get_heatmap(weeks: int = 12, granularity: str = "week", db: Session = Depends(get_db)):
    """资源负载热力矩阵（RESOURCE_HEATMAP §2.1）。

    - weeks：时间窗口长度（周数），0=全部（最早数据日期 → 今天）；负数 400
    - granularity：桶粒度 'week' | 'month'（非法值 400）
    - 注意：此静态路径必须注册在 /{resource_id}/workload 之前
    """
    if granularity not in ("week", "month"):
        raise HTTPException(400, f"granularity 非法：{granularity!r}（仅支持 week/month）")
    if weeks < 0:
        raise HTTPException(400, f"weeks 非法：{weeks}（须 ≥0，0=全部）")
    return build_heatmap(db, weeks=weeks, granularity=granularity)


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.scalars(select(Resource).where(Resource.name == payload.name)).first():
        raise HTTPException(400, f"人员 {payload.name} 已存在")
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.put("/{resource_id}", response_model=ResourceRead)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != resource.name:
        dup = db.scalars(select(Resource).where(Resource.name == data["name"])).first()
        if dup:
            raise HTTPException(400, f"人员 {data['name']} 已存在")
    for k, v in data.items():
        setattr(resource, k, v)
    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    db.delete(resource)
    db.commit()


@router.get("/{resource_id}/workload", response_model=ResourceWorkload)
def get_workload(resource_id: int, db: Session = Depends(get_db)):
    """某人负载：参与的所有项目/阶段（搁置项目/已完成/已搁置阶段除外，PROJECT_SHELVE §2.5）。"""
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(404, "人员不存在")
    phases: list[Phase] = [ph for ph in resource.phases if _workload_visible(ph)]
    return ResourceWorkload(
        resource={"id": resource.id, "name": resource.name, "role": resource.role},
        workloads=[_phase_to_workload(ph) for ph in phases],
    )
