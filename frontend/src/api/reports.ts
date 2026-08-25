import client from './client'
import type { WeeklyReport } from '../types'

export async function generateWeeklyReport(projectIds?: number[]): Promise<WeeklyReport> {
  const { data } = await client.post<WeeklyReport>('/reports/weekly', {
    project_ids: projectIds && projectIds.length > 0 ? projectIds : null,
  })
  return data
}
