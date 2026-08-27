// 与后端 Pydantic schema 一一对应的 TypeScript 类型定义

// 市场区域（与 docs/项目填报模板.xlsx 下拉一致）
export const MARKET_OPTIONS = [
  '拉美区', '西欧区', '东欧区', '中东区', '亚太区', '土耳其区', '非洲区', '北美区', 'OEM业务部',
]

export const MARKET_OPTION_ITEMS = MARKET_OPTIONS.map((m) => ({ value: m, label: m }))

// ---------- 项目 ----------
export interface Project {
  id: number
  code: string
  category: string // 新需求/量产/定制/改造
  name: string
  owner: string
  market: string // 销售区域（拉美区/西欧区/...）
  status: string // 未开始/进行中/已完成/搁置（旧值「已搁置」兼容显示，PROJECT_SHELVE §2.1）
  priority?: string | null // 高/中/低
  plan_start?: string | null // YYYY-MM-DD
  plan_end?: string | null
  template_id?: number | null
  remark?: string | null
  managed_by?: number | null // 项目负责人 user_id
  created_by?: number | null // 创建者 user_id
  created_at?: string | null
  updated_at?: string | null
  template?: { id: number; name: string; category: string } | null
  phases?: Phase[]
  is_favorite?: boolean // 当前用户是否关注（置顶）
}

export interface ProjectDetail extends Project {
  dependencies?: Dependency[]
}

export interface ProjectCreate {
  code?: string // 系统自动生成（连续整数），可不传
  category: string
  name: string
  owner: string
  market: string
  status?: string
  priority?: string | null
  plan_start?: string | null
  plan_end?: string | null
  template_id?: number | null
  remark?: string | null
  managed_by?: number | null // 项目负责人 user_id
}

export type ProjectUpdate = Partial<ProjectCreate>

// ---------- 阶段 ----------
export interface Phase {
  id: number
  project_id: number
  phase_type: string
  name: string
  sequence: number
  plan_start?: string | null
  plan_end?: string | null
  actual_start?: string | null
  actual_end?: string | null
  status: string // 未开始/进行中/已完成/延期/已搁置
  progress: number // 0-100
  rework_count: number
  remark?: string | null
  assignees?: Resource[]
}

export interface PhaseCreate {
  phase_type: string
  name: string
  sequence: number
  plan_start?: string | null
  plan_end?: string | null
  actual_start?: string | null
  actual_end?: string | null
  status?: string
  progress?: number
  remark?: string | null
  assignee_ids?: number[]
  depends_on_phase_ids?: number[]
  depended_by_phase_ids?: number[]
}

export type PhaseUpdate = Partial<PhaseCreate>

// ---------- 依赖 ----------
export interface Dependency {
  id: number
  from_phase_id: number
  to_phase_id: number
  type: string // FS/SS/FF/SF
  lag_days: number
}

export interface DependencyCreate {
  from_phase_id: number
  to_phase_id: number
  type?: string
  lag_days?: number
}

// ---------- 资源 ----------
export interface Resource {
  id: number
  name: string
  role?: string | null
  department?: string | null
  created_at?: string | null
}

export interface WorkloadItem {
  project_id: number
  project_name: string
  phase_id: number
  phase_name: string
  plan_start: string | null
  plan_end: string | null
  status: string | null
  period: (string | null)[]
}

export interface ResourceWorkload {
  resource: { id: number; name: string; role: string | null }
  workloads: WorkloadItem[]
}

// ---------- 资源负载热力矩阵（RESOURCE_HEATMAP §2.1） ----------

/** 冲突对详情（CONFLICT_MODEL_V2 评审处置 #2）：对方阶段/项目/重叠天数一次到位 */
export interface ConflictDetail {
  phase_a_id: number // 归一化：小 id 在前
  phase_b_id: number
  partner_name: string // 对方项目名
  partner_phase_name: string // 对方阶段名
  overlap_days: number
}

export interface HeatmapCellPhase {
  phase_id: number
  project_id: number
  project_name: string
  phase_name: string
  start: string // YYYY-MM-DD（plan 优先，仅实际日期阶段为 actual）
  end: string
  status: string | null
  conflict: boolean // 该人员视角真实冲突（检测剩余对，CONFLICT_MODEL_V2 §2.2）
  conflict_detail: ConflictDetail | null // 无冲突为 null
}

export interface HeatmapPerson {
  resource_id: number
  name: string
  role: string | null
  peak_parallel: number // 窗口内最大同时活跃数（扫描线）
  active_phases: number // 窗口内活跃阶段总数
  cells: number[] // 每周期相交活跃阶段数
  cell_phases: (HeatmapCellPhase[] | null)[]
}

export interface HeatmapIdlePerson {
  resource_id: number
  name: string
  role: string | null
}

export interface ResourceHeatmap {
  start_date: string
  end_date: string
  granularity: 'week' | 'month'
  columns: string[] // 每周期起始日
  people: HeatmapPerson[]
  idle_people: HeatmapIdlePerson[]
}

// ---------- 模板 ----------
export interface Template {
  id: number
  name: string
  category: string
  description?: string | null
  created_at?: string | null
}

// ---------- 甘特图数据（dhtmlxGantt 格式）----------
export interface GanttTask {
  id: number
  text: string
  start_date: string // YYYY-MM-DD
  duration: number
  progress: number
  parent: number
  type: string // "project" | "task"
  open?: boolean
  rework_count?: number | null
}

export interface GanttLink {
  id: number
  source: number
  target: number
  type: string // "0"=FS "1"=SS "2"=FF "3"=SF
  lag: number
}

export interface GanttData {
  data: GanttTask[]
  links: GanttLink[]
}

// ---------- 导入报告 ----------
export interface ImportError {
  row: number
  sheet: string
  field: string
  message: string
}

export interface ImportReport {
  total_rows: number
  projects_imported: number
  phases_imported: number
  resources_created: number
  errors: ImportError[]
  warnings: ImportError[]
  // 合并模式统计（替换模式为 0）
  projects_created: number
  projects_updated: number
  phases_created: number
  phases_updated: number
  pending_link_phases: { project_name: string; phase_name: string }[]
}

// 导入前差异报告（预览）
export interface ImportPreview {
  existing: { projects: number; phases: number; resources: number }
  incoming: { projects: number; phases: number }
  match: { matched: number; new: number; missing: number }
  errors: ImportError[]
  warnings: ImportError[]
  projects_preview: { name: string; market: string; category: string; phases: number }[]
  // 合并模式明细
  created_projects: { name: string; market: string; category: string; phases: number }[]
  updated_projects: { name: string; market: string; category: string; phases: number }[]
  kept_count: number
  phases_created: number
  phases_updated: number
  pending_link_phases: { project_name: string; phase_name: string }[]
}

// ---------- 首页看板 ----------
export interface StatusCount {
  status: string
  count: number
}

export interface DelayedProject {
  id: number
  code: string
  name: string
  owner: string
  market: string
  status: string
  plan_end: string | null
  overdue_days: number
}

export interface ReworkPhase {
  phase_id: number
  phase_name: string
  project_id: number
  project_name: string
  rework_count: number
}

// T5：阶段级延期 / 即将到期（看板）
export interface DelayedPhase {
  phase_id: number
  phase_name: string
  project_id: number
  project_name: string
  overdue_days: number
}

export interface DueSoonPhase {
  phase_id: number
  phase_name: string
  project_id: number
  project_name: string
  days_left: number
}

// T4：资源冲突
export interface ConflictPair {
  phase_a_id: number
  phase_a_name: string
  project_a_id: number
  project_a_name: string
  phase_b_id: number
  phase_b_name: string
  project_b_id: number
  project_b_name: string
  overlap_days: number
}

export interface ResourceConflict {
  resource_id: number
  resource_name: string
  conflicts: ConflictPair[]
}

// 冲突手动消除记录（CONFLICT_MODEL_V2 §2.3）
export interface ConflictOverride {
  id: number
  resource_id: number
  phase_a_id: number
  phase_b_id: number
  reason: string
  created_by: number | null
  created_at: string | null
}

export interface DashboardStats {
  total_projects: number
  active_projects: number
  delayed_count: number
  total_phases: number
  project_status: StatusCount[]
  phase_status: StatusCount[]
  delayed_projects: DelayedProject[]
  total_rework_count: number
  rework_phases: ReworkPhase[]
  // T5
  delayed_phases: DelayedPhase[]
  due_soon_phases: DueSoonPhase[]
  due_soon_count: number
  conflict_count: number
}

// ---------- 用户与认证 ----------
export interface UserInfo {
  id: number
  username: string
  name: string
  role: 'admin' | 'manager' | 'engineer' | 'viewer'
  is_active: boolean
  must_change_password: boolean
  resource_id?: number | null
  created_at?: string | null
}
