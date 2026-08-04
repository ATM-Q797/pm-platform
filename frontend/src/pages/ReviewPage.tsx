import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, Tabs, Modal, Input, message, Popconfirm } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { listDeleteRequests, reviewDeleteRequest, listOperationLogs } from '../api/audit'
import type { DeleteRequest, OperationLog } from '../api/audit'

const STATUS_TAG: Record<string, string> = {
  pending: 'processing',
  approved: 'success',
  rejected: 'error',
}
const STATUS_LABEL: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已拒绝',
}

export default function ReviewPage() {
  const [requests, setRequests] = useState<DeleteRequest[]>([])
  const [logs, setLogs] = useState<OperationLog[]>([])
  const [loading, setLoading] = useState(false)
  const [rejectModal, setRejectModal] = useState<DeleteRequest | null>(null)
  const [rejectComment, setRejectComment] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [reqs, lg] = await Promise.all([listDeleteRequests(), listOperationLogs(100)])
      setRequests(reqs)
      setLogs(lg)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleApprove = async (req: DeleteRequest) => {
    try {
      await reviewDeleteRequest(req.id, true, '审核通过')
      message.success(`已通过删除申请：${req.project_name}`)
      load()
    } catch (e) {
      message.error('审核失败：' + (e as Error).message)
    }
  }

  const handleRejectConfirm = async () => {
    if (!rejectModal) return
    try {
      await reviewDeleteRequest(rejectModal.id, false, rejectComment || '未填写')
      message.success('已拒绝删除申请')
      setRejectModal(null)
      setRejectComment('')
      load()
    } catch (e) {
      message.error('操作失败：' + (e as Error).message)
    }
  }

  // 删除申请表格列
  const reqColumns: ColumnsType<DeleteRequest> = [
    { title: '#', dataIndex: 'id', width: 50, align: 'center' },
    { title: '项目编号', dataIndex: 'project_code', width: 90, align: 'center' },
    { title: '项目名称', dataIndex: 'project_name' },
    { title: '申请人', dataIndex: 'requester_name', width: 100 },
    { title: '原因', dataIndex: 'reason', width: 200, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 100, align: 'center',
      render: (s: string) => <Tag color={STATUS_TAG[s]}>{STATUS_LABEL[s] || s}</Tag>,
    },
    { title: '申请时间', dataIndex: 'created_at', width: 160 },
    {
      title: '操作', width: 160, align: 'center',
      render: (_, r) => r.status === 'pending' ? (
        <Space>
          <Popconfirm title={`确认通过删除「${r.project_name}」？此操作不可恢复。`} onConfirm={() => handleApprove(r)}>
            <Button type="primary" danger size="small">通过</Button>
          </Popconfirm>
          <Button size="small" onClick={() => { setRejectModal(r); setRejectComment('') }}>拒绝</Button>
        </Space>
      ) : (
        <span style={{ color: '#999', fontSize: 12 }}>{r.review_comment || '-'}</span>
      ),
    },
  ]

  // 操作日志表格列
  const ACTION_LABEL: Record<string, string> = {
    create_project: '创建项目',
    update_project: '编辑项目',
    delete_project: '删除项目',
    request_delete_project: '申请删除',
    approve_delete_project: '通过删除',
    reject_delete_project: '拒绝删除',
    update_phase: '编辑阶段',
    rework_phase: '阶段返工',
  }
  const logColumns: ColumnsType<OperationLog> = [
    { title: '时间', dataIndex: 'created_at', width: 160 },
    { title: '操作人', dataIndex: 'user_name', width: 100 },
    {
      title: '操作', dataIndex: 'action', width: 110,
      render: (a: string) => <Tag>{ACTION_LABEL[a] || a}</Tag>,
    },
    { title: '对象', width: 120, render: (_, r) => `${r.target_type}${r.target_id ? '#' + r.target_id : ''}` },
    { title: '名称', dataIndex: 'target_name', width: 180, ellipsis: true },
    { title: '详情', dataIndex: 'detail', ellipsis: true },
  ]

  return (
    <Card title="审核中心" extra={<Button onClick={load}>刷新</Button>}>
      <Tabs
        items={[
          {
            key: 'requests',
            label: `删除申请${requests.filter(r => r.status === 'pending').length > 0 ? ` (${requests.filter(r => r.status === 'pending').length})` : ''}`,
            children: (
              <Table
                rowKey="id"
                columns={reqColumns}
                dataSource={requests}
                loading={loading}
                pagination={false}
                size="middle"
              />
            ),
          },
          {
            key: 'logs',
            label: '操作日志',
            children: (
              <Table
                rowKey="id"
                columns={logColumns}
                dataSource={logs}
                loading={loading}
                pagination={{ pageSize: 30, showSizeChanger: false }}
                size="middle"
              />
            ),
          },
        ]}
      />

      <Modal
        title="拒绝删除申请"
        open={!!rejectModal}
        onOk={handleRejectConfirm}
        onCancel={() => { setRejectModal(null); setRejectComment('') }}
        okText="确认拒绝"
      >
        <p>项目：{rejectModal?.project_name}</p>
        <Input.TextArea
          placeholder="拒绝原因（可选）"
          rows={3}
          value={rejectComment}
          onChange={(e) => setRejectComment(e.target.value)}
        />
      </Modal>
    </Card>
  )
}
