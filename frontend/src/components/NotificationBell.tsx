import { useCallback, useEffect, useRef, useState } from 'react'
import { Badge, Button, Empty, Popover, Tooltip, Typography, message } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { ReportNotificationItem } from '../types'
import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/report'

const { Text } = Typography

/** 顶栏通知铃铛（二期①，用户 2026-11-04）。
 *
 * 审批结果此前只在页面刷新时可查，且没有入口——通知是让「结果主动找到人」。
 * 15 秒轮询（仅页面可见时）+ 窗口聚焦/切回标签页立即刷新（用户 2026-11-04 体验反馈：
 * 原 60 秒轮询太钝，回来一看还是旧数字）；打开面板也会重拉一次。
 * 轮询失败不弹错误（顶栏噪音大），下一次轮询自然重试；点开列表失败才提示。
 */
export default function NotificationBell() {
  const [items, setItems] = useState<ReportNotificationItem[]>([])
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const openRef = useRef(false) // 面板是否打开：供轮询回调读取最新值（评审 #11 🔵）

  const loadCount = useCallback(async () => {
    try {
      setCount(await getUnreadNotificationCount())
    } catch {
      // 轮询静默失败：本地网络抖动/后端重启期间不打扰用户，下一轮自愈
    }
  }, [])

  const loadItems = useCallback(async () => {
    setLoading(true)
    try {
      setItems(await listNotifications(false))
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCount()
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      loadCount()
      // 面板开着时连列表一起重拉，否则会出现「角标 3、列表 2 条」（评审 #11 🔵）
      if (openRef.current) loadItems()
    }, 15000)
    const onFocus = () => loadCount()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') loadCount()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [loadCount])

  const openChange = (next: boolean) => {
    openRef.current = next
    setOpen(next)
    if (next) {
      loadItems()
      loadCount() // 打开面板再校一次未读数，避免看到列表与角标不一致
    }
  }

  const clickItem = async (n: ReportNotificationItem) => {
    if (!n.read_at) {
      try {
        await markNotificationRead(n.id)
        setCount((c) => Math.max(0, c - 1))
        setItems((list) => list.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)))
      } catch {
        // 标记已读失败不影响跳转：下次打开仍会显示未读，不会丢消息
      }
    }
    setOpen(false)
    if (n.link) navigate(n.link)
  }

  const content = (
    <div style={{ width: 340 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text strong>通知</Text>
        <Button
          size="small"
          type="link"
          disabled={count === 0}
          onClick={async () => {
            try {
              await markAllNotificationsRead()
              setCount(0)
              setItems((list) => list.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })))
              // 消除要有回伴：只看角标消失经常没注意到，补一句提示
              message.success('已全部标为已读')
            } catch (e) {
              message.error((e as Error).message)
            }
          }}
        >
          全部已读
        </Button>
      </div>
      <div style={{ maxHeight: 360, overflowY: 'auto' }}>
        {items.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知" />
        ) : (
          items.map((n) => (
            <div
              key={n.id}
              onClick={() => clickItem(n)}
              style={{
                padding: '8px 10px',
                borderRadius: 6,
                cursor: 'pointer',
                background: n.read_at ? 'transparent' : 'var(--bg-elevated, rgba(22,119,255,0.08))',
              }}
            >
              <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                {!n.read_at && <span style={{ color: '#1677ff', fontSize: 10 }}>●</span>}
                <Text strong={!n.read_at} style={{ fontSize: 13 }}>{n.title}</Text>
              </div>
              {n.body && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{n.body}</div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                {n.created_at ? n.created_at.replace('T', ' ').slice(0, 16) : ''}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )

  return (
    <Popover
      content={content}
      trigger="click"
      placement="bottomRight"
      open={open}
      onOpenChange={openChange}
    >
      <Tooltip title="通知">
        <Badge count={count} size="small" offset={[-2, 2]}>
          <Button type="text" icon={<BellOutlined style={{ fontSize: 18 }} />} />
        </Badge>
      </Tooltip>
    </Popover>
  )
}
