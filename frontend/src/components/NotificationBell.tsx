import { useCallback, useEffect, useState } from 'react'
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
 * 60 秒轮询一次：审批不需要秒级实时，但也不能让人永远等不到。
 * 轮询失败不弹错误（顶栏噪音大），下一次轮询自然重试；点开列表失败才提示。
 */
export default function NotificationBell() {
  const [items, setItems] = useState<ReportNotificationItem[]>([])
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

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
    const timer = window.setInterval(loadCount, 60000)
    return () => window.clearInterval(timer)
  }, [loadCount])

  const openChange = (next: boolean) => {
    setOpen(next)
    if (next) loadItems()
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
