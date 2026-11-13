import client from './client'

export interface PlanStabilityRow {
  project_id: number | null
  project_name: string | null
  change_count_project: number
  change_count_phase: number
  move_days_project: number
  move_days_phase: number
  move_days_total: number
}

export interface EstimationDeviationRow {
  project_id: number
  project_name: string | null
  phase_id: number
  phase_name: string | null
  first_plan_start: string
  first_plan_end: string
  actual_start: string | null
  actual_end: string
  plan_duration_days: number
  actual_duration_days: number | null
  deviation_days: number | null
  delivery_deviation_days: number
}

export interface ApprovalLatency {
  avg_hours: number | null
  count: number
  approved_avg_hours: number | null
  approved_count: number
}

export interface ProcessAuditResult {
  days: number
  data_start: string | null
  plan_stability: PlanStabilityRow[]
  estimation_deviation: EstimationDeviationRow[]
  approval_latency: ApprovalLatency
  move_parse_skipped: number
  first_plan_skipped: number
}

/** 过程审计三指标（P3）：days 30/90/365 三档；market 锚 Project.market（可选）；project_id 单项目明细（可选） */
export async function getProcessAudit(params: {
  days: number
  market?: string
  project_id?: number
}): Promise<ProcessAuditResult> {
  const { data } = await client.get<ProcessAuditResult>('/analysis/process-audit', {
    params: { days: params.days, market: params.market || undefined, project_id: params.project_id },
  })
  return data
}
