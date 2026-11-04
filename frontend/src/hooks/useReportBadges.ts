import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReportBadges } from '../types'
import { getReportBadges } from '../api/report'

const EMPTY: ReportBadges = { approvals: 0, mine: 0, notifications: 0 }

/** 填报页角标轮询（用户 2026-11-04 体验反馈）。
 *
 * 为什么需要这个 hook：此前「待我审批」的角标由该标签页自己加载后回填——不点进去
 * 就一直是 0；铃铛另有一套 60 秒轮询。三处刷新时机不同，用户看到的就是「不及时」。
 * 这里把三个数合成一条链：15 秒轮询（仅页面可见时）+ 窗口聚焦 + 标签页切回时立即重拉，
 * 业务动作（提交/审批/已读）后由调用方调 refresh() 立即刷新，做到「做完就变」。
 */
export default function useReportBadges() {
  const [badges, setBadges] = useState<ReportBadges>(EMPTY)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const inFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (inFlight.current) return // 并发点击/聚焦不叠加请求
    inFlight.current = true
    setRefreshing(true)
    try {
      setBadges(await getReportBadges())
      setUpdatedAt(new Date())
    } catch {
      // 轮询静默失败：下一轮或聚焦会重试；手动刷新失败时的提示由调用方决定
    } finally {
      inFlight.current = false
      setRefreshing(false)
    }
  }, [])

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

  return { badges, refresh, updatedAt, refreshing }
}
