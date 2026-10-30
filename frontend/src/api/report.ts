import client from './client'
import type {
  ReportChangeRequestItem,
  ReportMeta,
  ReportPhaseRow,
  ReportProjectCreatePayload,
  ReportProjectDetail,
  ReportProjectItem,
} from '../types'

// ---------- 信息填报 API（信息填报一期 §六，8 接口） ----------

export async function listReportProjects(): Promise<ReportProjectItem[]> {
  const { data } = await client.get<ReportProjectItem[]>('/report/projects')
  return data
}

export async function getReportProject(id: number): Promise<ReportProjectDetail> {
  const { data } = await client.get<ReportProjectDetail>(`/report/projects/${id}`)
  return data
}

export async function createReportProject(
  payload: ReportProjectCreatePayload,
): Promise<ReportProjectDetail> {
  const { data } = await client.post<ReportProjectDetail>('/report/projects', payload)
  return data
}

export async function patchReportProject(
  id: number,
  payload: Record<string, unknown>,
): Promise<ReportProjectDetail> {
  const { data } = await client.patch<ReportProjectDetail>(`/report/projects/${id}`, payload)
  return data
}

export async function patchReportPhase(
  phaseId: number,
  payload: Record<string, unknown>,
): Promise<ReportPhaseRow> {
  const { data } = await client.patch<ReportPhaseRow>(`/report/phases/${phaseId}`, payload)
  return data
}

export async function createReportChangeRequest(payload: {
  phase_id: number
  plan_start?: string | null
  plan_end?: string | null
  name?: string | null
  phase_type?: string | null
  sequence?: number | null
  assignee_ids?: number[] | null
}): Promise<ReportChangeRequestItem> {
  const { data } = await client.post<ReportChangeRequestItem>('/report/change-requests', payload)
  return data
}

/** 新增一行阶段（用户 2026-10-30 指令）：插到 afterPhaseId 之后，null → 追加末尾 */
export async function createReportPhase(
  projectId: number,
  payload: { phase_type: string; after_phase_id?: number | null },
): Promise<ReportPhaseRow> {
  const { data } = await client.post<ReportPhaseRow>(`/report/projects/${projectId}/phases`, payload)
  return data
}

/** 删除一行阶段（用户 2026-10-30 指令）：服务端重排 sequence，不可恢复 */
export async function deleteReportPhase(phaseId: number): Promise<void> {
  await client.delete(`/report/phases/${phaseId}`)
}

/** 删除项目（用户 2026-10-29 需求 3）：仅项目负责人及管理员，不可恢复 */
export async function deleteReportProject(projectId: number): Promise<void> {
  await client.delete(`/report/projects/${projectId}`)
}

export async function listReportChangeRequests(): Promise<ReportChangeRequestItem[]> {
  const { data } = await client.get<ReportChangeRequestItem[]>('/report/change-requests')
  return data
}

export async function reviewReportChangeRequest(
  id: number,
  payload: { approved: boolean; comment?: string | null },
): Promise<ReportChangeRequestItem> {
  const { data } = await client.post<ReportChangeRequestItem>(
    `/report/change-requests/${id}/review`,
    payload,
  )
  return data
}

export async function getReportMeta(): Promise<ReportMeta> {
  const { data } = await client.get<ReportMeta>('/report/meta')
  return data
}
