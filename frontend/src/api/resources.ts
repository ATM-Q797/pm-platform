import client from './client'
import type { Resource, ResourceWorkload } from '../types'

export async function listResources(): Promise<Resource[]> {
  const { data } = await client.get<Resource[]>('/resources')
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
