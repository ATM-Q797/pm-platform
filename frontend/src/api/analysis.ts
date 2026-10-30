import client from './client'
import type { AnalysisTrend, SnapshotRunResult } from '../types'

/** 趋势数据：日级点位 + 周级聚合（差分由后端查询时算好，weekly.delta） */
export async function getAnalysisTrend(days: 30 | 90 | 180): Promise<AnalysisTrend> {
  const { data } = await client.get<AnalysisTrend>('/analysis/trend', { params: { days } })
  return data
}

/** 手动触发当日快照（admin；幂等：首次建行、同日 skipped）
 *  force=true（分析弹窗"数据刷新"按钮）：当日已有也重新采集覆盖，立即反映最新数据 */
export async function runSnapshot(force = false): Promise<SnapshotRunResult> {
  const { data } = await client.post<SnapshotRunResult>(
    '/analysis/snapshots/run',
    null,
    { params: force ? { force: true } : {} },
  )
  return data
}
