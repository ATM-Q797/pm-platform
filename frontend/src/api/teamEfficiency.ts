import client from './client'

export interface PersonMetrics {
  resource_id: number
  name: string
  role: string | null
  active_projects: number
  peak_parallel: number
  on_time_rate: number | null
  on_time_sample: string
  rework_rate: number | null
  avg_cycle_days: number | null
  active_phases: number
}

export interface EfficiencySummary {
  completion_date_record_rate: number | null
  total_phases: number
  dated_phases: number
  window_label: string
}

export interface ReworkTopItem {
  phase_type: string
  name: string
  on_time_rate: number | null
  on_time_sample: string
}

export interface TeamEfficiency {
  window_days: number
  summary: EfficiencySummary
  persons: PersonMetrics[]
  role_load: Record<string, number>
  rework_top: ReworkTopItem[]
}

export async function listTeamEfficiency(days?: number): Promise<TeamEfficiency> {
  const { data } = await client.get<TeamEfficiency>('/team-efficiency', { params: { days } })
  return data
}
