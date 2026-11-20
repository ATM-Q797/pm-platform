import client from './client'
import type { GanttData } from '../types'

/** 进行中项目总览甘特数据（一次聚合请求：项目行负 id + 阶段子行 + 跨项目依赖连线） */
export async function getOverviewGantt(): Promise<GanttData> {
  const { data } = await client.get<GanttData>('/projects/overview-gantt')
  return data
}
