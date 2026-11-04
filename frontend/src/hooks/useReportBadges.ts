import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReportBadges } from '../types'
import { getReportBadges } from '../api/report'

const EMPTY: ReportBadges = { approvals: 0, mine: 0 }

const same = (a: ReportBadges, b: ReportBadges) =>
  a.approvals === b.approvals && a.mine === b.mine

/** 填报页角标轮询（用户 2026-11-04 体验反馈；评审 #11 修正）。
 *
 * 三条链路的取舍：
 * ① 15 秒轮询（仅页面可见）+ 聚焦/切回立即重拉 —— 解决「不及时」；
 * ② 业务动作后的刷新**不丢弃**：正在飞时记为尾随任务，当前请求结束后补跑一次
 *    （原实现直接 return，慢网络下「做完就变」会落空）；
 * ③ 失败有出口：`failed` 交给调用方渲染成「更新失败」，与「本来就是 0」区分开
 *    （静默失败会让用户读成「没有待办」）。
 * `refreshing` 只代表手动刷新，后台轮询不再让按钮自己转圈。
 */
export default function useReportBadges() {
  const [badges, setBadges] = useState<ReportBadges>(EMPTY)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [failed, setFailed] = useState(false)
  const inFlight = useRef(false)
  const queued = useRef(false)

  const fetchOnce = useCallback(async (): Promise<boolean> => {
    try {
      const next = await getReportBadges()
      // 三个数都没变就复用旧对象：避免每 15 秒让整棵填报页重渲染一次
      setBadges((prev) => (same(prev, next) ? prev : next))
      setUpdatedAt(new Date())
      setFailed(false)
      return true
    } catch {
      setFailed(true)
      return false
    }
  }, [])

  const refresh = useCallback(async (opts?: { manual?: boolean }): Promise<boolean> => {
    if (inFlight.current) {
      queued.current = true // 尾随合并：这次刷新不丢，等当前请求结束后补跑
      return false
    }
    inFlight.current = true
    if (opts?.manual) setRefreshing(true)
    try {
      return await fetchOnce()
    } finally {
      inFlight.current = false
      if (opts?.manual) setRefreshing(false)
      if (queued.current) {
        queued.current = false
        void refresh()
      }
    }
  }, [fetchOnce])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') refresh()
    }, 15000)
    const onFocus = () => refresh()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [refresh])

  return { badges, refresh, updatedAt, refreshing, failed }
}
