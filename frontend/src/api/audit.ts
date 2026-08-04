import client from './client'

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
