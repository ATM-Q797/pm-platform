import client from './client'
import type { UserInfo } from '../types'

export interface LoginResult {
  user: UserInfo
  must_change_password: boolean
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const { data } = await client.post<LoginResult>('/auth/login', { username, password })
  return data
}

export async function logout(): Promise<void> {
  await client.post('/auth/logout')
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await client.get<UserInfo>('/auth/me')
  return data
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.put('/auth/password', { old_password: oldPassword, new_password: newPassword })
}
