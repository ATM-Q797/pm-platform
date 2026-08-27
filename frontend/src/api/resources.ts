import client from './client'
import type {
  ConflictOverride,
  Resource,
  ResourceConflict,
  ResourceHeatmap,
  ResourceWorkload,
} from '../types'

export async function listResources(): Promise<Resource[]> {
  const { data } = await client.get<Resource[]>('/resources')
  return data
}

export async function getHeatmap(params: { weeks: number; granularity: 'week' | 'month' }): Promise<ResourceHeatmap> {
  const { data } = await client.get<ResourceHeatmap>('/resources/heatmap', { params })
  return data
}

export async function getResourceWorkload(id: number): Promise<ResourceWorkload> {
  const { data } = await client.get<ResourceWorkload>(`/resources/${id}/workload`)
  return data
}

export async function getAllWorkloads(): Promise<ResourceWorkload[]> {
  const { data } = await client.get<ResourceWorkload[]>('/resources/all/workload')
  return data
}

export async function createResource(payload: { name: string; role?: string; department?: string }): Promise<Resource> {
  const { data } = await client.post<Resource>('/resources', payload)
  return data
}

export async function getResourceConflicts(): Promise<ResourceConflict[]> {
  const { data } = await client.get<ResourceConflict[]>('/resources/conflicts')
  return data
}

// ---- 冲突手动消除（CONFLICT_MODEL_V2 §2.3） ----

export async function createConflictOverride(
  resourceId: number,
  payload: { phase_a_id: number; phase_b_id: number; reason: string },
): Promise<ConflictOverride> {
  const { data } = await client.post<ConflictOverride>(
    `/resources/conflicts/${resourceId}/override`,
    payload,
  )
  return data
}

export async function listConflictOverrides(): Promise<ConflictOverride[]> {
  const { data } = await client.get<ConflictOverride[]>('/resources/conflicts/overrides')
  return data
}

export async function deleteConflictOverride(overrideId: number): Promise<void> {
  await client.delete(`/resources/conflicts/overrides/${overrideId}`)
}
