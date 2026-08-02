import client from './client'
import type { Phase, PhaseCreate, PhaseUpdate, Dependency, DependencyCreate } from '../types'

export async function listPhases(projectId: number): Promise<Phase[]> {
  const { data } = await client.get<Phase[]>(`/projects/${projectId}/phases`)
  return data
}

export async function getPhase(id: number): Promise<Phase> {
  const { data } = await client.get<Phase>(`/phases/${id}`)
  return data
}

export async function createPhase(projectId: number, payload: PhaseCreate): Promise<Phase> {
  const { data } = await client.post<Phase>(`/projects/${projectId}/phases`, payload)
  return data
}

export async function updatePhase(id: number, payload: PhaseUpdate): Promise<Phase> {
  const { data } = await client.put<Phase>(`/phases/${id}`, payload)
  return data
}

export async function deletePhase(id: number): Promise<void> {
  await client.delete(`/phases/${id}`)
}

export async function reworkPhase(
  id: number,
  payload: { to_status?: string; reason: string }
): Promise<void> {
  await client.post(`/phases/${id}/rework`, payload)
}

// ---------- 依赖 ----------
export async function listDependencies(projectId: number): Promise<Dependency[]> {
  const { data } = await client.get<Dependency[]>(`/projects/${projectId}/dependencies`)
  return data
}

export async function createDependency(
  projectId: number,
  payload: DependencyCreate
): Promise<Dependency> {
  const { data } = await client.post<Dependency>(`/projects/${projectId}/dependencies`, payload)
  return data
}

export async function deleteDependency(id: number): Promise<void> {
  await client.delete(`/dependencies/${id}`)
}
