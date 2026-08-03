import client from './client'
import type { Template } from '../types'

export async function listTemplates(): Promise<Template[]> {
  const { data } = await client.get<Template[]>('/templates')
  return data
}
