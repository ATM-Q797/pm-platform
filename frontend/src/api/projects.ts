import client from './client'
import type { Project, ProjectCreate, ProjectUpdate, ProjectDetail, GanttData } from '../types'

export async function listProjects(params?: {
  status?: string
  category?: string
  market?: string
}): Promise<Project[]> {
  const { data } = await client.get<Project[]>('/projects', { params })
  return data
}

export async function getProject(id: number): Promise<ProjectDetail> {
  const { data } = await client.get<ProjectDetail>(`/projects/${id}`)
  return data
}

export async function createProject(payload: ProjectCreate): Promise<Project> {
  const { data } = await client.post<Project>('/projects', payload)
  return data
}

export async function updateProject(id: number, payload: ProjectUpdate): Promise<Project> {
  const { data } = await client.put<Project>(`/projects/${id}`, payload)
  return data
}

export async function deleteProject(id: number): Promise<void> {
  await client.delete(`/projects/${id}`)
}

export async function getProjectGantt(id: number): Promise<GanttData> {
  const { data } = await client.get<GanttData>(`/projects/${id}/gantt`)
  return data
}

export async function applyTemplate(projectId: number, templateId: number): Promise<Project> {
  const { data } = await client.post<Project>(`/projects/${projectId}/apply-template/${templateId}`)
  return data
}
