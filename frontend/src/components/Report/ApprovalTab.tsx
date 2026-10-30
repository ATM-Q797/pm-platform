import { useCallback, useEffect, useState } from 'react'
import { Button, Empty, Input, Modal, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ReportChangeRequestItem } from '../../types'
import { listReportChangeRequests, reviewReportChangeRequest } from '../../api/report'
import { describeProposal } from './ChangeRequestModal'

const { Text } = Typography

/** Tab2 待我审批（§五/§九-4）：仅项目负责人可见，批准/驳回在填报页内闭环。 */
export default function ApprovalTab({
  onCountChange,
  onChanged,
}: {
  onCountChange: (n: number) => void
  onChanged: () => void
}) {
  const [rows, setRows] = useState<ReportChangeRequestItem[]>([])
  const [loading, setLoading] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<ReportChangeRequestItem | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listReportChangeRequests()
      setRows(data)
      onCountChange(data.length)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [onCountChange])

  useEffect(() => {
    load()
  }, [load])

  const review = async (item: ReportChangeRequestItem, approved: boolean, comment?: string) => {
    try {
      await reviewReportChangeRequest(item.id, { approved, comment: comment ?? null })
      message.success(approved ? '已批准，计划时间已更新' : '已驳回')
      load()
      onChanged()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const columns: ColumnsType<ReportChangeRequestItem> = [
    { title: '项目编号', dataIndex: 'project_code', width: 90 },
    { title: '项目', dataIndex: 'project_name', width: 180, ellipsis: true },
    { title: '阶段', dataIndex: 'phase_name', width: 130 },
    { title: '申请人', dataIndex: 'requester_name', width: 100 },
    {
      title: '变更内容',
      key: 'proposed',
      render: (_: unknown, r) => <Text>{describeProposal(r)}</Text>,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string | null) => (v ? v.replace('T', ' ').slice(0, 16) : '—'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: unknown, r) => (
        <Space>
          <Button size="small" type="primary" onClick={() => review(r, true)}>
            批准
          </Button>
          <Button
            size="small"
            danger
            onClick={() => {
              setRejectTarget(r)
              setRejectReason('')
            }}
          >
            驳回
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {rows.length === 0 && !loading ? (
        <Empty description="暂无待审批的改期申请" style={{ margin: '40px 0' }} />
      ) : (
        <Table<ReportChangeRequestItem>
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
        />
      )}
      <Modal
        title={`驳回改期申请 — ${rejectTarget?.phase_name ?? ''}`}
        open={rejectTarget !== null}
        onCancel={() => setRejectTarget(null)}
        onOk={async () => {
          if (!rejectReason.trim()) {
            message.warning('请填写驳回原因')
            return
          }
          if (rejectTarget) {
            await review(rejectTarget, false, rejectReason.trim())
            setRejectTarget(null)
          }
        }}
        okText="确认驳回"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text type="secondary">
            <Tag color="orange">待审</Tag>
            {rejectTarget ? describeProposal(rejectTarget) : ''}
          </Text>
          <Input.TextArea
            rows={3}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="驳回原因（必填，申请人可见）"
            maxLength={200}
          />
        </Space>
      </Modal>
    </div>
  )
}
