"""信息填报服务层（信息填报一期）——权限判定与审批机制的单一来源。

设计 docs/信息填报模块设计方案.md：
- §3.2 三种数据级身份（项目负责人 managed_by / 阶段负责人 assignees / 其他只读）
- §四 改期审批（复用 phase_change_request，单 pending、负责人直改作废）
- 字段级 editable 白名单在此判定，router 只做薄封装。

阶段负责人判定：user.resource_id → 该阶段 assignees 含此 Resource（deps.py:96-99 同口径）。
项目负责人判定：project.managed_by == user.id（deps.py:77 同口径）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Phase,
    PhaseChangeRequest,
    Project,
    Resource,
    User,
    phase_assignee,
)
from app.routers.audit import log_operation
from app.routers.phases import _sync_assignees

# 项目级字段 editable 白名单（按 §3.2：仅项目负责人可改项目级字段）
PROJECT_FIELDS = ("category", "name", "market", "status", "remark", "managed_by")
# 阶段字段 editable 白名单（按 §3.2 分身份；assignee_ids 指派为项目负责人专属——设计 §二/验收 8）
PHASE_FIELD_OWNER = ("phase_type", "name", "sequence", "assignee_ids")  # 项目负责人专属
PHASE_FIELD_ASSIGNEE = ("actual_start", "actual_end", "status", "progress", "remark")
PHASE_FIELD_OWNER_DIRECT = ("plan_start", "plan_end")  # 负责人直改；阶段负责人走审批
# 新建项目类目三选一（§二：定制归一为新需求，存量值兼容显示）
REPORT_CATEGORIES = ("新需求", "量产升级", "改造")
# 项目级搁置状态（与 dashboard.py:_SHELVED_PROJECT_STATUSES 同源口径——搁置项目=假完成，
# 名下阶段不参与逾期/临期报警；project_overdue_flags 用）
_SHELVED_PROJECT_STATUSES = ("搁置",)


# ---------- 身份判定 ----------

def is_project_owner(project: Project, user: User) -> bool:
    """项目负责人：managed_by == user.id，姓名回退（deps.py:77 现有口径 + 用户 2026-10-30 指令）。

    admin 具有全部修改权限（用户 2026-10-29 指令：管理员具有所有的修改权限，无需审批）
    → admin 一律视为 owner（editable 全开、可直改计划时间）。
    姓名回退（用户 2026-10-30 指令「项目负责人和登录的填报人匹配后即为此项目负责人」）：
    Excel 导入项目 managed_by 为空、owner 文本 = 账号名 → 判 owner，权限与「我负责」
    标记（is_project_manager）一致——我负责=全部修改权限（is_mine 判定与权限判定不脱节）。
    """
    if user.role == "admin":
        return True
    if project.managed_by is not None:
        return project.managed_by == user.id
    return project.owner == user.name


def is_phase_assignee(phase: Phase, user: User) -> bool:
    """阶段负责人：user.resource_id → 该阶段 assignees 包含此 Resource。

    姓名回退（用户 2026-10-29 指令"参与者无任何可编辑空间"根因修复）：填报人账号可能
    未关联 resource_id（平台账号+填报账号并存，resource_id 常为空）——此时按姓名匹配
    阶段 assignees（资源名全局唯一，与 deps.py managed_by 历史回退同法）。
    """
    if user.resource_id:
        return any(r.id == user.resource_id for r in phase.assignees)
    return any(r.name == user.name for r in phase.assignees)


def get_report_role(project: Project, phase: Phase | None, user: User) -> str:
    """数据级身份：owner / assignee / viewer（§3.2 三行）。"""
    if is_project_owner(project, user):
        return "owner"
    if phase is not None and is_phase_assignee(phase, user):
        return "assignee"
    return "viewer"


def _403(field: str, reason: str) -> HTTPException:
    return HTTPException(403, f"无权修改字段「{field}」：{reason}")


def check_project_patch(project: Project, user: User, data: dict) -> None:
    """项目级字段级校验（§六：越权字段整请求 403 附字段名，明细取首个字段）。"""
    if not data:
        raise HTTPException(400, "未提供任何修改字段")
    # 负责人字段固定（用户 2026-10-29 权限分级需求 2）：仅管理员可改——
    # 填报人/负责人本人均不可改（写入侧强制，防绕过前端直改）
    if "managed_by" in data and user.role != "admin":
        raise _403("managed_by", "负责人字段已固定，仅管理员可修改")
    if not is_project_owner(project, user):
        raise _403(next(iter(data)), "仅项目负责人可修改项目级字段")


def phase_editable_map(project: Project, phase: Phase, user: User) -> dict[str, bool]:
    """单阶段逐字段 editable 标记（§六 GET 下发，前端只做显示裁剪）。"""
    role = get_report_role(project, phase, user)
    e = {f: False for f in (
        *PHASE_FIELD_OWNER, *PHASE_FIELD_ASSIGNEE, *PHASE_FIELD_OWNER_DIRECT)}
    if role == "owner":
        for f in e:
            e[f] = True
    elif role == "assignee":
        for f in PHASE_FIELD_ASSIGNEE:
            e[f] = True
    return e


def check_phase_patch(
    db: Session, project: Project, phase: Phase, user: User, data: dict
) -> dict:
    """阶段字段级校验（§3.2 + §六）。越权即 403 并附字段名；返回裁剪后的可落库 data。

    - 项目负责人：全部字段直改（plan_* 直改并触发 pending 申请作废）；
    - 阶段负责人：actual_*/status/progress/remark；plan_* 不可改 → 403 引导走申请接口；
      assignee_ids 指派是项目负责人专属（§二/验收 8），同样 403；
    - 其他：全字段 403。
    """
    if not data:
        raise HTTPException(400, "未提供任何修改字段")
    role = get_report_role(project, phase, user)
    if role == "viewer":
        raise _403(next(iter(data)), "仅项目负责人或阶段负责人可修改该阶段")
    allowed = set(PHASE_FIELD_ASSIGNEE) if role == "assignee" else {
        *PHASE_FIELD_ASSIGNEE, *PHASE_FIELD_OWNER, *PHASE_FIELD_OWNER_DIRECT}
    for f in data:
        if f not in allowed:
            if f in PHASE_FIELD_OWNER_DIRECT and role == "assignee":
                raise _403(f, "阶段负责人修改计划时间请走改期申请接口（POST /api/report/change-requests）")
            raise _403(f, "无该字段修改权限")
    if role == "owner" and ({"plan_start", "plan_end"} & set(data)):
        _invalidate_pending_on_direct_edit(db, phase, user)
    return data


# ---------- 单 pending 与直改作废（§四边界规则） ----------

def get_pending_request(db: Session, phase_id: int) -> PhaseChangeRequest | None:
    """该阶段当前 pending 的改期申请（单一 pending 语义，audit.py:181-189 同口径）。"""
    return db.scalars(
        select(PhaseChangeRequest).where(
            PhaseChangeRequest.phase_id == phase_id,
            PhaseChangeRequest.status == "pending",
        )
    ).first()


def _invalidate_pending_on_direct_edit(db: Session, phase: Phase, user: User) -> None:
    """负责人直改计划时间 → 该阶段 pending 申请自动置 rejected（§四边界规则 2）。"""
    pending = get_pending_request(db, phase.id)
    if pending is not None:
        pending.status = "rejected"
        pending.reviewed_by = user.id
        pending.review_comment = "负责人已直接改期，申请作废"
        pending.reviewed_at = datetime.now()
        log_operation(
            db, user, "invalidate_phase_change", "phase", phase.id, phase.name,
            detail=f"负责人直接改期，自动作废待审申请 #{pending.id}",
        )


# ---------- 改期申请：提案构造与解析 ----------

def build_change_proposal(phase: Phase, plan_start: date | None, plan_end: date | None,
                          name: str | None = None, phase_type: str | None = None,
                          sequence: int | None = None, assignee_ids: list[int] | None = None) -> str:
    """构造提案 JSON（§四格式）：old 取 Phase 现值，new 取申请值；未变的字段不出现。

    用户 2026-10-29 需求 4 泛化：支持 name/phase_type/sequence/assignee_ids——
    参与者点击修改负责人专属字段同样走审批（审批后生效）。
    """
    proposal: dict = {}
    if plan_start is not None:
        proposal["plan_start"] = {
            "old": phase.plan_start.isoformat() if phase.plan_start else None,
            "new": plan_start.isoformat(),
        }
    if plan_end is not None:
        proposal["plan_end"] = {
            "old": phase.plan_end.isoformat() if phase.plan_end else None,
            "new": plan_end.isoformat(),
        }
    if name is not None and name != phase.name:
        proposal["name"] = {"old": phase.name, "new": name}
    if phase_type is not None and phase_type != phase.phase_type:
        proposal["phase_type"] = {"old": phase.phase_type, "new": phase_type}
    if sequence is not None and sequence != phase.sequence:
        proposal["sequence"] = {"old": phase.sequence, "new": sequence}
    if assignee_ids is not None and assignee_ids != [r.id for r in phase.assignees]:
        proposal["assignee_ids"] = {
            "old": [r.id for r in phase.assignees],
            "new": assignee_ids,
        }
    return json.dumps(proposal, ensure_ascii=False)


def parse_change_proposal(proposed_changes: str | None) -> dict:
    """解析提案 JSON；兼容旧工程师流的平铺格式 {field: value}，归一为 {field: {old,new}}。"""
    if not proposed_changes:
        return {}
    try:
        raw = json.loads(proposed_changes)
    except (TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k, v in raw.items():
        if isinstance(v, dict) and ("old" in v or "new" in v):
            out[k] = v
        else:
            out[k] = {"old": None, "new": v}
    return out


def apply_change_proposal(db: Session, req: PhaseChangeRequest, user: User) -> None:
    """批准：应用提案到 Phase + 写操作日志（§四流程 2；audit.py:248-263 同模式）。"""
    phase = db.get(Phase, req.phase_id)
    if phase is None:
        raise HTTPException(404, "阶段不存在")
    changes = parse_change_proposal(req.proposed_changes)
    # 倒挂区间防护（批准门）：提交与批准之间现值可能漂移（负责人直改未作废的旧流申请），落库前再校验一次
    ps = phase.plan_start if "plan_start" not in changes else (
        date.fromisoformat(changes["plan_start"]["new"]) if changes["plan_start"]["new"] else None)
    pe = phase.plan_end if "plan_end" not in changes else (
        date.fromisoformat(changes["plan_end"]["new"]) if changes["plan_end"]["new"] else None)
    if ps and pe and pe < ps:
        raise HTTPException(400, "计划结束不得早于计划开始，请驳回后重新申请")
    for field, payload in changes.items():
        new = payload.get("new")
        if field in ("plan_start", "plan_end"):
            setattr(phase, field, date.fromisoformat(new) if new else None)
        elif field == "assignee_ids":
            # 多对多关系：setattr 不生效，走同步函数（含存在性校验）
            _sync_assignees(db, phase, [int(x) for x in (new or [])])
        elif field == "sequence":
            phase.sequence = int(new)
        elif field == "phase_type":
            from app.routers.report import _PHASE_TYPE_NAMES  # 阶段类型枚举（P1..P9，router 常量）
            if new not in _PHASE_TYPE_NAMES:
                raise HTTPException(400, f"阶段类型非法（仅支持平台 10 类）：{new}")
            phase.phase_type = new
            # 阶段名自动跟随类型显示名（§二：PhaseEditor 同规则）
            phase.name = _PHASE_TYPE_NAMES[new]
        elif field == "name":
            if not str(new or "").strip():
                raise HTTPException(400, "阶段名称不得为空")
            phase.name = str(new).strip()
        else:
            setattr(phase, field, new)
    # sequence 变更后重排项目内所有阶段（保证连续无空洞，§二既有规则）
    if "sequence" in changes:
        from app.routers.phases import _normalize_sequence
        _normalize_sequence(db, phase.project_id)
    phase_name = phase.name
    log_operation(
        db, user, "approve_report_phase_change", "phase", req.phase_id, phase_name,
        detail=f"批准改期申请 #{req.id}：{json.dumps(changes, ensure_ascii=False)}",
    )


# ---------- 项目进度（§五 Tab1：名下阶段 progress 均值） ----------

def project_progress(phases: list[Phase]) -> int | None:
    """项目进度 = 名下阶段 progress 均值；无阶段返回 None（前端显示"—"）。"""
    if not phases:
        return None
    return round(sum(p.progress or 0 for p in phases) / len(phases))


def project_overdue_flags(project: Project, phases: list[Phase]) -> tuple[bool, bool]:
    """项目逾期/即将到期标记（用户 2026-10-30 指令，与看板 dashboard 同口径）。

    逾期 = 名下存在已逾期活跃阶段（plan_end < 今天 且 阶段状态未完成/未搁置）；
    即将到期 = plan_end 在未来 7 天内（含今天）且阶段状态未完成/未搁置。
    口径基准 = 看板"延期项目"（T4）而非"即将到期阶段"（T5）：T4 的阶段过滤即
    ~(已完成/搁置) 含"延期"状态（dashboard.py:72），T5 则仅认 未开始/进行中
    （dashboard.py:163）——两个看板面自身不同，填报页标识是项目级（同 T4 语义），
    故阶段状态集合对齐 T4。项目搁置（假完成）整体不标——搁置项目的阶段不参与任何
    阶段级报警（看板 _SHELVED_PROJECT_STATUSES 约定，dashboard.py:30-32）；
    阶段锚定（方案 A，2026-09-03）——整体 plan_end 不参与判定。
    """
    if project.status in _SHELVED_PROJECT_STATUSES:
        return False, False
    today = date.today()
    overdue = False
    due_soon = False
    for ph in phases:
        if ph.status in ("已完成", "搁置"):
            continue
        if ph.plan_end is None:
            continue
        if ph.plan_end < today:
            overdue = True
        if today <= ph.plan_end <= today + timedelta(days=7):
            due_soon = True
    # 两标记独立上报（一个项目可同时有已逾期阶段与 7 天内到期阶段，如埃塞VTM：
    # 10-27 样机/线缆打样未开始已逾期 + 11-03 联调/交付未开始临期）——展示优先级由前端定
    return overdue, due_soon


# ---------- 可见范围 ----------

def visible_projects(db: Session, user: User) -> list[Project]:
    """填报视角可见项目（§3.1）：全量普通项目（专项排除，与 GET /api/projects 同口径）。"""
    return list(db.scalars(
        select(Project).where(Project.is_special.is_(False)).order_by(Project.id)
    ))


def involved_project_ids(db: Session, user: User) -> set[int]:
    """我（resource）参与阶段的项目 id 集合（projects.py:71-78 同口径）。

    姓名回退（用户 2026-10-29 根因修复，is_phase_assignee 同法）：resource_id 为空的
    账号按姓名唯一匹配资源——平台账号+填报账号并存时同样可见"我参与"。
    """
    if user.resource_id:
        res_id = user.resource_id
    else:
        res = db.scalar(select(Resource).where(Resource.name == user.name))
        if res is None:
            return set()
        res_id = res.id
    rows = db.execute(
        select(phase_assignee.c.phase_id).where(
            phase_assignee.c.resource_id == res_id
        )
    ).all()
    phase_ids = [r[0] for r in rows]
    if not phase_ids:
        return set()
    return {
        pid for (pid,) in db.execute(
            select(Phase.project_id).where(Phase.id.in_(phase_ids))
        ).all()
    }


def is_project_manager(db: Session, user: User, project: Project) -> bool:
    """该项目负责人是否为当前填报人（用户 2026-10-30 指令：「我负责」判定口径）。

    判定顺序：① 账号严格匹配（managed_by == user.id）；② 姓名回退——Excel 导入项目
    负责人仅文本无账号（managed_by=None 但 owner 文本 = 账号名），按用户裁定
    「项目负责人和登录的填报人匹配后即为项目负责人」判 is_mine，权限随 is_project_owner
    下发。与 involved_project_ids 的姓名回退同法。
    """
    if project.managed_by is not None:
        return project.managed_by == user.id
    return project.owner == user.name


def next_code(db: Session) -> str:
    """编号预览：普通项目数字序列下一个编号（与创建同源，见 services/project_code.py）。"""
    from app.services.project_code import next_project_code
    return next_project_code(db)


def resolve_assignees(db: Session, assignee_ids: list[int]) -> list[Resource]:
    """校验并取回阶段负责人 Resource 列表（不存在即 400）。"""
    if not assignee_ids:
        return []
    resources = list(db.scalars(select(Resource).where(Resource.id.in_(assignee_ids))))
    found = {r.id for r in resources}
    missing = set(assignee_ids) - found
    if missing:
        raise HTTPException(400, f"人员 id 不存在: {sorted(missing)}")
    return resources


def sync_phase_assignees(db: Session, phase: Phase, assignee_ids: list[int]) -> None:
    """整体替换阶段负责人（内部经 resolve_assignees 校验后复用 phases.py 的既有实现）。"""
    resolve_assignees(db, assignee_ids)
    _sync_assignees(db, phase, assignee_ids)
