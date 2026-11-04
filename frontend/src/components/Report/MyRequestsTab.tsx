import { useCallback, useEffect, useState } from 'react'
import { Empty, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ReportMyChangeRequestItem } from '../../types'
import { listMyChangeRequests } from '../../api/report'
import { describeProposal } from './ChangeRequestModal'

const { Text } = Typography

const STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: 'orange', label: '待审批' },
  approved: { color: 'green', label: '已批准' },
  rejected: { color: 'red', label: '已驳回' },
}

/** 「我的申请」（二期①，用户 2026-11-04）：申请人查看自己提交的变更申请与结果。
 *
 * 此前只有「待我审批」（给审批人），申请人提交后无从查看：被驳回时连理由都看不到
 * （驳回理由只由旧审核中心渲染，而 reporter 被角色隔离挡在旧页面之外）。
 */
export default function MyRequestsTab() {
  const [rows, setRows] = useState<ReportMyChangeRequestItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await listMyChangeRequests())
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const columns: ColumnsType<ReportMyChangeRequestItem> = [
    { title: '项目', dataIndex: 'project_name', width: 180, ellipsis: true },
    { title: '阶段', dataIndex: 'phase_name', width: 120 },
    {
      title: '变更内容',
      key: 'proposed',
      render: (_: unknown, r) => <Text>{describeProposal(r)}</Text>,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      width: 150,
      render: (v: string | null) => (v ? v.replace('T', ' ').slice(0, 16) : '—'),
    },
    {
      title: '结果',
      dataIndex: 'status',
      width: 110,
      render: (v: string, r: ReportMyChangeRequestItem) => {
        // 「已作废」由后端结构化标记下发（invalidated），不再匹配驳回原因文案：
        // 文案一旦改词就会静默退化成「已驳回」，反之人工理由含同样字样也会误判。
        if (r.invalidated) {
          return <Tag>已作废</Tag>
        }
        const m = STATUS_META[v] ?? { color: 'default', label: v }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '审批人 / 说明',
      key: 'review',
      render: (_: unknown, r) =>
        r.status === 'pending' ? (
          <Text type="secondary">等待审批</Text>
        ) : (
          <div style={{ fontSize: 12 }}>
            {r.reviewer_name && <div>{r.reviewer_name}</div>}
            {r.review_comment && <Text type="secondary">{r.review_comment}</Text>}
            {r.reviewed_at && (
              <div style={{ color: 'var(--text-tertiary)' }}>
                {r.reviewed_at.replace('T', ' ').slice(0, 16)}
              </div>
            )}
          </div>
        ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary">
          我提交的变更申请及审批结果（倒序）。被驳回或作废时会显示审批人与原因。
        </Text>
      </div>
      {rows.length === 0 && !loading ? (
        <Empty description="暂无提交过的变更申请" style={{ margin: '40px 0' }} />
      ) : (
        <Table<ReportMyChangeRequestItem>
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
        />
      )}
    </div>
  )
}
