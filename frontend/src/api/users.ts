import client from './client'
import type { UserInfo } from '../types'

export interface UserCreatePayload {
  username: string
  name: string
  role: string
  password?: string
  resource_id?: number | null
}

export async function listUsers(): Promise<UserInfo[]> {
  const { data } = await client.get<UserInfo[]>('/users')
  return data
}

export async function createUser(payload: UserCreatePayload): Promise<UserInfo> {
  const { data } = await client.post<UserInfo>('/users', payload)
  return data
}

export async function updateUser(
  id: number,
  payload: Partial<{ name: string; role: string; is_active: boolean; resource_id: number | null }>
): Promise<UserInfo> {
  const { data } = await client.put<UserInfo>(`/users/${id}`, payload)
  return data
}

export async function deleteUser(id: number): Promise<void> {
  await client.delete(`/users/${id}`)
}

export async function resetPassword(id: number): Promise<void> {
  await client.post(`/users/${id}/reset-password`)
}
