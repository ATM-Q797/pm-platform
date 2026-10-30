"""信息填报 API（信息填报一期，前缀 /api/report）。

设计 docs/信息填报模块设计方案.md §六——8 接口：
- GET  /api/report/projects                     项目列表（Tab1 卡片）
- POST /api/report/projects                     新建项目（reporter/admin/manager）
- GET  /api/report/projects/{id}                项目+阶段明细（逐字段 editable）
- PATCH /api/report/phases/{id}                 阶段字段级更新（越权 403 附字段名）
- POST /api/report/change-requests              提交改期申请（阶段负责人）
- GET  /api/report/change-requests              待我审批（项目负责人）
- POST /api/report/change-requests/{id}/review  批准/驳回（项目负责人）
- GET  /api/report/meta                         枚举+选人+编号预览

权限判定一律下沉 services/report_service.py（单一来源）；旧路由零改动，
reporter 对既有 API 的封锁由 main.py 的全局 gate 实现（REPORT lockdown）。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import (
    OperationLog,
    Phase,
    PhaseChangeRequest,
    Project,
    User,
)
from app.routers.audit import log_operation
from app.schemas.report import (
    ReportChangeRequestCreate,
    ReportChangeRequestItem,
    ReportChangeReview,
    ReportMeta,
    ReportPhaseOut,
    ReportPhasePatch,
    ReportProjectCreate,
    ReportProjectCreatePhase,
    ReportProjectDetail,
    ReportProjectItem,
)
from app.services import report_service as svc

router = APIRouter(prefix="/api/report", tags=["信息填报"])

# 与平台既有下拉一致（§六：字段口径与现有平台完全一致）
PROJECT_STATUSES = ("未开始", "进行中", "已完成", "搁置")
PHASE_STATUSES = ("未开始", "进行中", "已完成", "延期", "搁置")


def _load_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.is_special:
        raise HTTPException(404, "项目不存在")
    return project


def _load_phase(db: Session, phase_id: int) -> tuple[Phase, Project]:
    phase = db.get(Phase, phase_id)
    if phase is None:
        raise HTTPException(404, "阶段不存在")
    project = db.get(Project, phase.project_id)
    if project is None or project.is_special:
        raise HTTPException(404, "阶段不存在")
    return phase, project


def _managed_by_name(db: Session, project: Project) -> str | None:
    if project.managed_by is None:
        # 未关联负责人账号时回退 owner 文本（用户 2026-10-30 指令：与项目列表负责人字段对应——
        # Excel 导入的项目负责人多为文本、无对应账号，此前填报页显示空）
        return project.owner or None
    m = db.get(User, project.managed_by)
    if not m:
        return project.owner or None
    # 墓碑用户（强制删除）显示后缀——指派保留，历史不失真（用户 2026-10-29 裁定）
    return f"{m.name}（已强制删除）" if m.force_deleted_at else m.name


# ---------- Tab1：项目列表 ----------

@router.get("/projects", response_model=list[ReportProjectItem])
def list_report_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """填报视角项目列表：按项目计划开始时间排序（与项目列表页同序），附参与标记与项目进度均值（§五 Tab1）。"""
    projects = svc.visible_projects(db, user)
    involved_ids = svc.involved_project_ids(db, user)
    items: list[ReportProjectItem] = []
    for p in projects:
        items.append(ReportProjectItem(
            id=p.id,
            code=p.code,
            name=p.name,
            category=p.category,
            owner=p.owner,
            market=p.market,
            status=p.status,
            remark=p.remark,
            managed_by=p.managed_by,
            managed_by_name=_managed_by_name(db, p),
            progress=svc.project_progress(p.phases),
            # 「我负责」判定（用户 2026-10-30 指令）：负责人账号匹配 → 姓名回退（Excel 导入
            # 项目 managed_by 空、owner 文本=账号名），svc.is_project_manager 单一来源；
            # admin 不例外（admin 的全权修改走 is_project_owner，与此显示标记解耦）
            is_mine=svc.is_project_manager(db, user, p),
            involved=p.id in involved_ids,
            phase_count=len(p.phases),
            **dict(zip(("overdue", "due_soon"), svc.project_overdue_flags(p, p.phases))),
        ))
    # 顺序已由 svc.visible_projects 统一按计划开始时间给出（与 /api/projects 同一条规则）——
    # 不再二次按 id 排序，否则两页面顺序会分叉（用户 2026-10-30 指令）
    return items


# ---------- 新建项目（§九-2：reporter/admin/manager；managed_by 缺省=自己） ----------

@router.post("/projects", response_model=ReportProjectDetail, status_code=status.HTTP_201_CREATED)
def create_report_project(
    payload: ReportProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in ("reporter", "admin", "manager"):
        raise HTTPException(403, "仅填报人/管理员/项目负责人可新建项目")
    if payload.category not in svc.REPORT_CATEGORIES:
        raise HTTPException(400, f"项目类目非法：{payload.category}（可选：{'/'.join(svc.REPORT_CATEGORIES)}）")
    if payload.status not in PROJECT_STATUSES:
        raise HTTPException(400, f"项目状态非法：{payload.status}")
    if payload.managed_by is None:
        payload.managed_by = user.id  # §九-2：默认自己是负责人
    manager = db.get(User, payload.managed_by)
    if manager is None:
        raise HTTPException(400, f"项目负责人 id {payload.managed_by} 不存在")
    if manager.force_deleted_at is not None:
        raise HTTPException(400, "该用户已强制删除，不可指派为项目负责人")  # 评审 #4

    # 行级校验（§5.1：行序即 sequence，行级校验结束>开始；§九-3 阶段类型仅平台 10 类）
    for idx, row in enumerate(payload.phases, start=1):
        if row.phase_type not in _PHASE_TYPE_NAMES:
            raise HTTPException(400, f"第 {idx} 行阶段：类型非法（仅支持平台 10 类）")
        if row.plan_start and row.plan_end and row.plan_end < row.plan_start:
            raise HTTPException(400, f"第 {idx} 行阶段：计划结束不得早于计划开始")

    # 编号可选（用户 2026-10-29：编号不重要可不填）：留空/缺省自动递增；填了查重
    code = (payload.code or "").strip() or svc.next_code(db)
    if db.scalars(select(Project).where(Project.code == code)).first():
        raise HTTPException(400, f"项目编号 {code} 已存在")
    project = Project(
        code=code,
        category=payload.category,
        name=payload.name,
        owner=manager.name,  # owner 文本存显示名（§二映射）
        market=payload.market,
        status=payload.status,
        remark=payload.remark,
        managed_by=payload.managed_by,
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    for idx, row in enumerate(payload.phases, start=1):
        phase = Phase(
            project_id=project.id,
            phase_type=row.phase_type,
            name=_phase_type_name(row.phase_type),
            sequence=idx,  # 行序即 sequence（§二）
            plan_start=row.plan_start,
            plan_end=row.plan_end,
            status="未开始",
            progress=0,
        )
        db.add(phase)
        db.flush()
        svc.sync_phase_assignees(db, phase, row.assignee_ids)
    log_operation(db, user, "create_project", "project", project.id, project.name,
                  detail=f"填报页新建（负责人：{manager.name}，{len(payload.phases)} 个阶段）")
    db.commit()
    db.refresh(project)
    return get_report_project(project.id, db=db, user=user)


_PHASE_TYPE_NAMES = {
    "P1": "需求评估", "P2": "配置评估", "P3": "模块选型", "P4": "工业设计",
    "P5": "结构设计", "P6": "线缆设计", "P71": "样机打样", "P72": "线缆打样",
    "P8": "联调测试", "P9": "交付",
}


def _phase_type_name(phase_type: str) -> str:
    """阶段名自动取类型显示名（§二：PhaseEditor 已去名称输入的先例）。"""
    return _PHASE_TYPE_NAMES.get(phase_type, phase_type)


# ---------- 项目详情（逐字段 editable） ----------

@router.get("/projects/{project_id}", response_model=ReportProjectDetail)
def get_report_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _load_project(db, project_id)
    is_owner = svc.is_project_owner(project, user)
    project_editable = {f: is_owner for f in svc.PROJECT_FIELDS}
    # 负责人字段固定（用户 2026-10-29 权限分级需求 2）：项目创建/明确负责人后即固定——
    # 填报人/负责人本人均不可改，仅管理员可修改
    project_editable["managed_by"] = user.role == "admin"
    phases_out: list[ReportPhaseOut] = []
    for ph in sorted(project.phases, key=lambda x: x.sequence):
        e = svc.phase_editable_map(project, ph, user)
        pending = svc.get_pending_request(db, ph.id)
        phases_out.append(ReportPhaseOut(
            id=ph.id,
            phase_type=ph.phase_type,
            name=ph.name,
            sequence=ph.sequence,
            plan_start=ph.plan_start,
            plan_end=ph.plan_end,
            actual_start=ph.actual_start,
            actual_end=ph.actual_end,
            status=ph.status,
            progress=ph.progress,
            remark=ph.remark,
            assignees=ph.assignees,
            assignee_ids=[r.id for r in ph.assignees],
            editable=e,
            can_request_change=svc.is_phase_assignee(ph, user),
            has_pending=pending is not None,
        ))
    return ReportProjectDetail(
        id=project.id,
        code=project.code,
        name=project.name,
        category=project.category,
        owner=project.owner,
        market=project.market,
        status=project.status,
        remark=project.remark,
        managed_by=project.managed_by,
        managed_by_name=_managed_by_name(db, project),
        is_mine=is_owner,
        can_delete=svc.is_project_owner(project, user),
        editable=project_editable,
        phases=phases_out,
    )


# ---------- 项目级字段更新（项目负责人） ----------

@router.patch("/projects/{project_id}", response_model=ReportProjectDetail)
def patch_report_project(
    project_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """项目级字段更新（§3.2：仅项目负责人；越权字段整请求 403 附字段名）。

    dict 直收后过白名单校验：非法/越权字段名在服务层 403，不静默丢弃。
    """
    project = _load_project(db, project_id)
    unknown = set(payload) - set(svc.PROJECT_FIELDS)
    if unknown:
        raise HTTPException(400, f"不支持的项目级字段：{sorted(unknown)}")
    # 值类型前置收敛（dict 直收无 Pydantic 校验）：错误类型一律 400，避免落库层 500
    _PROJECT_FIELD_TYPES = {"category": str, "name": str, "market": str, "status": str, "remark": str, "managed_by": int}
    for k, v in payload.items():
        expected = _PROJECT_FIELD_TYPES[k]
        if not isinstance(v, expected) or isinstance(v, bool) and expected is int:
            raise HTTPException(400, f"字段「{k}」类型非法：期望 {expected.__name__}")
    svc.check_project_patch(project, user, payload)
    if "category" in payload and payload["category"] not in svc.REPORT_CATEGORIES:
        raise HTTPException(400, f"项目类目非法：{payload['category']}")
    if "status" in payload and payload["status"] not in PROJECT_STATUSES:
        raise HTTPException(400, f"项目状态非法：{payload['status']}")
    if "managed_by" in payload:
        manager = db.get(User, payload["managed_by"])
        if manager is None:
            raise HTTPException(400, f"项目负责人 id {payload['managed_by']} 不存在")
        if manager.force_deleted_at is not None:
            raise HTTPException(400, "该用户已强制删除，不可指派为项目负责人")  # 评审 #4
        project.owner = manager.name
    for k, v in payload.items():
        setattr(project, k, v)
    log_operation(db, user, "update_project", "project", project.id, project.name,
                  detail=f"填报页修改字段：{', '.join(payload.keys())}")
    db.commit()
    db.refresh(project)
    return get_report_project(project.id, db=db, user=user)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除项目（用户 2026-10-29 权限分级需求 3）：仅项目负责人及管理员。

    物理删除（不可恢复）：全部引用表均有 ondelete=CASCADE（phase/phase_assignee/
    phase_change_request/user_favorite/project_delete_request/rework_log/dependency/
    conflict_override），DB 级联清理；操作日志为文本快照无外键，审计链保留。
    """
    project = _load_project(db, project_id)
    if not svc.is_project_owner(project, user):
        raise HTTPException(403, "仅项目负责人及管理员可删除项目")
    log_operation(db, user, "delete_project", "project", project.id, project.name,
                  detail=f"填报页删除项目「{project.name}」（不可恢复）")
    db.delete(project)  # 级联：phases（ORM cascade）+ 各引用表（DB ondelete=CASCADE）
    db.commit()


# ---------- 阶段字段级更新 ----------

@router.patch("/phases/{phase_id}", response_model=ReportPhaseOut)
def patch_report_phase(
    phase_id: int,
    payload: ReportPhasePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    phase, project = _load_phase(db, phase_id)
    data = payload.model_dump(exclude_unset=True)
    data = svc.check_phase_patch(db, project, phase, user, data)
    if "status" in data and data["status"] not in PHASE_STATUSES:
        raise HTTPException(400, f"阶段状态非法：{data['status']}")
    if "phase_type" in data and data["phase_type"] not in _PHASE_TYPE_NAMES:
        raise HTTPException(400, f"阶段类型非法（仅支持平台 10 类）：{data['phase_type']}")
    if "name" in data and not str(data["name"] or "").strip():
        raise HTTPException(400, "阶段名称不得为空")
    if data.get("plan_start") and data.get("plan_end") and data["plan_end"] < data["plan_start"]:
        raise HTTPException(400, "计划结束不得早于计划开始")
    # 单字段更新也防倒挂：与库内现值合并校验
    ps = data.get("plan_start", phase.plan_start)
    pe = data.get("plan_end", phase.plan_end)
    if ps and pe and pe < ps:
        raise HTTPException(400, "计划结束不得早于计划开始")
    assignee_ids = data.pop("assignee_ids", None)
    for k, v in data.items():
        setattr(phase, k, v)
    # 类型变更 → 名称自动跟随类型显示名（§二：PhaseEditor 同规则；申请路径 report_service 同口径）
    if "phase_type" in data:
        phase.name = _PHASE_TYPE_NAMES[data["phase_type"]]
    if assignee_ids is not None and svc.is_project_owner(project, user):
        svc.sync_phase_assignees(db, phase, assignee_ids)
    log_operation(db, user, "update_phase", "phase", phase.id, phase.name,
                  detail=f"填报页修改字段：{', '.join(data.keys())}")
    # sequence 变更后重排项目内所有阶段（保证连续无空洞，§二既有规则；与申请路径同口径）
    # 注意：_normalize_sequence 只改内存不 commit——必须在其后统一 commit（phases.py 既有模式）
    if "sequence" in data:
        from app.routers.phases import _normalize_sequence
        _normalize_sequence(db, phase.project_id)
    db.commit()
    db.refresh(phase)
    e = svc.phase_editable_map(project, phase, user)
    pending = svc.get_pending_request(db, phase.id)
    return ReportPhaseOut(
        id=phase.id,
        phase_type=phase.phase_type,
        name=phase.name,
        sequence=phase.sequence,
        plan_start=phase.plan_start,
        plan_end=phase.plan_end,
        actual_start=phase.actual_start,
        actual_end=phase.actual_end,
        status=phase.status,
        progress=phase.progress,
        remark=phase.remark,
        assignees=phase.assignees,
        assignee_ids=[r.id for r in phase.assignees],
        editable=e,
        can_request_change=svc.is_phase_assignee(phase, user),
        has_pending=pending is not None,
    )


# ---------- 改期申请（§四） ----------

@router.post("/change-requests", response_model=ReportChangeRequestItem,
             status_code=status.HTTP_201_CREATED)
def create_report_change_request(
    payload: ReportChangeRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """阶段负责人提交变更申请（写 pending，不落 Phase）。

    用户 2026-10-29 需求 4 泛化：除计划时间外，名称/类型/顺序/阶段负责人的修改
    同样走审批——其他字段点击修改触发审核，审核人为项目负责人。
    """
    phase, project = _load_phase(db, payload.phase_id)
    if svc.is_project_owner(project, user):
        raise HTTPException(400, "项目负责人请直接修改，无需申请")
    if not svc.is_phase_assignee(phase, user):
        raise HTTPException(403, "仅阶段负责人可提交变更申请")
    if svc.get_pending_request(db, phase.id) is not None:
        raise HTTPException(400, "该阶段已有待审批的变更申请")
    # 倒挂区间防护（与 PATCH 同口径）：申请值与 Phase 现值合并校验
    ps = payload.plan_start if payload.plan_start is not None else phase.plan_start
    pe = payload.plan_end if payload.plan_end is not None else phase.plan_end
    if ps and pe and pe < ps:
        raise HTTPException(400, "计划结束不得早于计划开始")
    # 值合法性（批准前先拦，避免批准时才失败）
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(400, "阶段名称不得为空")
    if payload.phase_type is not None and payload.phase_type not in _PHASE_TYPE_NAMES:
        raise HTTPException(400, f"阶段类型非法（仅支持平台 10 类）：{payload.phase_type}")
    if payload.sequence is not None and payload.sequence < 1:
        raise HTTPException(400, "顺序须为正整数")
    if payload.assignee_ids is not None and len(payload.assignee_ids) == 0:
        raise HTTPException(400, "阶段负责人不得为空（至少保留一人）")
    # 单 pending 之外，还要拦同人在既有工程师流里的重复（同表同语义）
    req = PhaseChangeRequest(
        phase_id=phase.id,
        project_id=project.id,
        requested_by=user.id,
        proposed_changes=svc.build_change_proposal(
            phase, payload.plan_start, payload.plan_end,
            name=payload.name, phase_type=payload.phase_type,
            sequence=payload.sequence, assignee_ids=payload.assignee_ids,
        ),
        status="pending",
    )
    db.add(req)
    log_operation(db, user, "request_phase_change", "phase", phase.id, phase.name,
                  detail=f"提交变更申请（项目：{project.name}）")
    db.commit()
    db.refresh(req)
    return _change_item(db, req)


@router.get("/change-requests", response_model=list[ReportChangeRequestItem])
def list_report_change_requests(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """待我审批（Tab2 角标数据源）：我负责项目的 pending 改期申请。"""
    rows = db.scalars(
        select(PhaseChangeRequest)
        .join(Project, PhaseChangeRequest.project_id == Project.id)
        .where(
            Project.managed_by == user.id,
            PhaseChangeRequest.status == "pending",
        )
        .order_by(PhaseChangeRequest.created_at.desc(), PhaseChangeRequest.id.desc())
    ).all()
    return [_change_item(db, r) for r in rows]


@router.post("/change-requests/{req_id}/review", response_model=ReportChangeRequestItem)
def review_report_change_request(
    req_id: int,
    payload: ReportChangeReview,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批准（应用+写操作日志）/ 驳回（原因必填）——仅项目负责人（§四）。"""
    req = db.get(PhaseChangeRequest, req_id)
    if req is None:
        raise HTTPException(404, "申请不存在")
    project = db.get(Project, req.project_id)
    if project is None or not svc.is_project_owner(project, user):
        raise HTTPException(403, "仅项目负责人可审批")
    if req.status != "pending":
        raise HTTPException(400, f"该申请已处理（当前状态：{req.status}）")
    if not payload.approved and not (payload.comment and payload.comment.strip()):
        raise HTTPException(400, "驳回必须填写原因")

    req.reviewed_by = user.id
    req.review_comment = payload.comment
    req.reviewed_at = datetime.now()
    if payload.approved:
        req.status = "approved"
        svc.apply_change_proposal(db, req, user)
    else:
        req.status = "rejected"
        log_operation(db, user, "reject_report_phase_change", "phase", req.phase_id,
                      detail=f"驳回改期申请 #{req.id}，原因：{payload.comment}")
    db.commit()
    db.refresh(req)
    return _change_item(db, req)


def _change_item(db: Session, req: PhaseChangeRequest) -> ReportChangeRequestItem:
    phase = db.get(Phase, req.phase_id)
    project = db.get(Project, req.project_id)
    requester = db.get(User, req.requested_by)
    return ReportChangeRequestItem(
        id=req.id,
        phase_id=req.phase_id,
        phase_name=phase.name if phase else None,
        project_id=req.project_id,
        project_name=project.name if project else None,
        project_code=project.code if project else None,
        requester_name=(f"{requester.name}（已强制删除）" if requester and requester.force_deleted_at else (requester.name if requester else None)),  # 评审 #5：与负责人同款墓碑后缀
        proposed=svc.parse_change_proposal(req.proposed_changes),
        status=req.status,
        review_comment=req.review_comment,
        created_at=req.created_at,
    )


# ---------- 元数据 ----------

@router.get("/meta", response_model=ReportMeta)
def get_report_meta(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """类目/市场/状态/阶段类型枚举 + 选人下拉 + 编号预览（§六）。"""
    from app.models import Resource
    users = db.scalars(select(User).where(User.is_active.is_(True), User.force_deleted_at.is_(None)).order_by(User.id)).all()
    resources = db.scalars(select(Resource).order_by(Resource.id)).all()
    return ReportMeta(
        categories=list(svc.REPORT_CATEGORIES),
        markets=[
            "拉美区", "西欧区", "东欧区", "中东区", "亚太区",
            "土耳其区", "非洲区", "北美区", "OEM业务部", "海外通用",
        ],
        project_statuses=list(PROJECT_STATUSES),
        phase_statuses=list(PHASE_STATUSES),
        phase_types=[{"value": k, "label": v} for k, v in _PHASE_TYPE_NAMES.items()],
        users=[{"id": u.id, "name": u.name, "role": u.role} for u in users],
        resources=[{"id": r.id, "name": r.name, "role": r.role} for r in resources],
        next_code=svc.next_code(db),
    )
