import client from './client'

// ---------- 过程事件（P1 过程事件地基，PHASE8_PLAN §九） ----------
export interface DataChangeEvent {
  id: number
  project_id: number | null
  phase_id: number | null
  field: string
  field_label: string | null
  old_value: string | null
  new_value: string | null
  source: string  // direct_edit | report_edit | approval | rework
  changed_by: number | null
  changed_by_name: string | null
  project_name: string | null
  phase_name: string | null
  reason: string | null
  created_at: string | null
}

export interface DataChangeEventQuery {
  project_id?: number
  phase_id?: number
  field?: string
  source?: string
  days?: number
  limit?: number
}

export async function listDataChangeEvents(params?: DataChangeEventQuery): Promise<DataChangeEvent[]> {
  const { data } = await client.get<DataChangeEvent[]>('/data-change-events', { params })
  return data
}

// ---------- 删除申请 ----------
export interface DeleteRequest {
  id: number
  project_id: number
  project_name: string | null
  project_code: string | null
  requested_by: number
  requester_name: string | null
  reason: string | null
  status: string  // pending / approved / rejected
  reviewed_by: number | null
  review_comment: string | null
  created_at: string | null
  reviewed_at: string | null
}

export async function requestDeleteProject(projectId: number, reason?: string): Promise<DeleteRequest> {
  const { data } = await client.post<DeleteRequest>(`/projects/${projectId}/delete-request`, { reason })
  return data
}

export async function listDeleteRequests(statusFilter?: string): Promise<DeleteRequest[]> {
  const params = statusFilter ? { status: statusFilter } : {}
  const { data } = await client.get<DeleteRequest[]>('/delete-requests', { params })
  return data
}

export async function reviewDeleteRequest(reqId: number, approved: boolean, comment?: string): Promise<DeleteRequest> {
  const { data } = await client.post<DeleteRequest>(`/delete-requests/${reqId}/review`, { approved, comment })
  return data
}

// ---------- 操作日志 ----------
export interface OperationLog {
  id: number
  user_name: string | null
  action: string
  target_type: string
  target_id: number | null
  target_name: string | null
  detail: string | null
  created_at: string | null
}

export async function listOperationLogs(limit = 50): Promise<OperationLog[]> {
  const { data } = await client.get<OperationLog[]>('/operation-logs', { params: { limit } })
  return data
}

// ---------- 阶段编辑审批 ----------
export interface PhaseChangeRequest {
  id: number
  phase_id: number
  phase_name: string | null
  project_id: number
  project_name: string | null
  requested_by: number
  requester_name: string | null
  proposed_changes: string | null
  status: string
  reviewed_by: number | null
  review_comment: string | null
  created_at: string | null
  reviewed_at: string | null
}

export async function createPhaseChangeRequest(phaseId: number, proposedChanges: Record<string, any>): Promise<PhaseChangeRequest> {
  const { data } = await client.post<PhaseChangeRequest>('/phase-change-requests', {
    phase_id: phaseId,
    proposed_changes: proposedChanges,
  })
  return data
}

export async function listPhaseChangeRequests(statusFilter?: string): Promise<PhaseChangeRequest[]> {
  const params = statusFilter ? { status: statusFilter } : {}
  const { data } = await client.get<PhaseChangeRequest[]>('/phase-change-requests', { params })
  return data
}

export async function reviewPhaseChangeRequest(reqId: number, approved: boolean, comment?: string): Promise<PhaseChangeRequest> {
  const { data } = await client.post<PhaseChangeRequest>(`/phase-change-requests/${reqId}/review`, { approved, comment })
  return data
}
