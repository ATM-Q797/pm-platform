import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, Tabs, Modal, Input, message, Popconfirm, Popover } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { listDeleteRequests, reviewDeleteRequest, listOperationLogs, listPhaseChangeRequests, reviewPhaseChangeRequest } from '../api/audit'
import type { DeleteRequest, OperationLog, PhaseChangeRequest } from '../api/audit'

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

export default function ReviewPage({ userRole = 'admin' }: { userRole?: string }) {
  const [requests, setRequests] = useState<DeleteRequest[]>([])
  const [phaseChanges, setPhaseChanges] = useState<PhaseChangeRequest[]>([])
  const [logs, setLogs] = useState<OperationLog[]>([])
  const [loading, setLoading] = useState(false)
  const [rejectModal, setRejectModal] = useState<DeleteRequest | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  // 阶段变更拒绝
  const [phaseRejectId, setPhaseRejectId] = useState<number | null>(null)
  const [phaseRejectName, setPhaseRejectName] = useState('')
  const [phaseRejectComment, setPhaseRejectComment] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const results = await Promise.all([
        userRole === 'admin' ? listDeleteRequests() : Promise.resolve([]),
        listPhaseChangeRequests('pending'),
        userRole === 'admin' ? listOperationLogs(100) : Promise.resolve([]),
      ])
      setRequests(results[0])
      setPhaseChanges(results[1])
      setLogs(results[2])
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

  // 阶段变更审批
  const handlePhaseApprove = async (req: PhaseChangeRequest) => {
    try {
      await reviewPhaseChangeRequest(req.id, true, '审核通过')
      message.success(`已通过变更审批：${req.phase_name}`)
      load()
    } catch (e) {
      message.error('审批失败：' + (e as Error).message)
    }
  }

  const handlePhaseReject = (req: PhaseChangeRequest) => {
    setPhaseRejectId(req.id)
    setPhaseRejectName(req.phase_name || '')
    setPhaseRejectComment('')
  }

  const handlePhaseRejectConfirm = async () => {
    if (!phaseRejectId) return
    try {
      await reviewPhaseChangeRequest(phaseRejectId, false, phaseRejectComment || '未填写')
      message.success('已拒绝变更申请')
      setPhaseRejectId(null)
      setPhaseRejectComment('')
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
    submit_phase_change: '提交阶段变更',
    approve_phase_change: '通过阶段变更',
    reject_phase_change: '拒绝阶段变更',
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

  // 阶段变更字段中文映射
  const FIELD_LABEL: Record<string, string> = {
    status: '状态',
    progress: '进度',
    plan_start: '计划开始',
    plan_end: '计划结束',
    actual_start: '实际开始',
    actual_end: '实际结束',
    phase_type: '阶段类型',
    remark: '备注',
    assignee_ids: '负责人',
  }

  /** 解析 proposed_changes JSON，返回可读的变更摘要 */
  const formatChanges = (jsonStr: string | null): { items: { field: string; value: string }[]; summary: string } => {
    if (!jsonStr) return { items: [], summary: '无变更' }
    try {
      const obj = JSON.parse(jsonStr)
      const items = Object.entries(obj).map(([key, value]) => ({
        field: FIELD_LABEL[key] || key,
        value: String(value ?? '—'),
      }))
      const summary = items.map(i => `${i.field}: ${i.value}`).join('；')
      return { items, summary: summary || '无变更' }
    } catch {
      return { items: [], summary: jsonStr }
    }
  }

  // 阶段变更审批列
  const phaseColumns: ColumnsType<PhaseChangeRequest> = [
    { title: '#', dataIndex: 'id', width: 50, align: 'center' },
    { title: '项目', dataIndex: 'project_name', width: 160, ellipsis: true },
    { title: '阶段', dataIndex: 'phase_name', width: 120 },
    { title: '申请人', dataIndex: 'requester_name', width: 100 },
    {
      title: '状态', dataIndex: 'status', width: 100, align: 'center',
      render: (s: string) => <Tag color={STATUS_TAG[s]}>{STATUS_LABEL[s] || s}</Tag>,
    },
    { title: '提交时间', dataIndex: 'created_at', width: 160 },
    {
      title: '变更内容', dataIndex: 'proposed_changes', width: 200, ellipsis: true,
      render: (json: string | null) => {
        const { summary, items } = formatChanges(json)
        if (items.length === 0) return <span style={{ color: '#999' }}>{summary}</span>
        const content = (
          <div style={{ maxWidth: 320 }}>
            {items.map((item, i) => (
              <div key={i} style={{ marginBottom: 4 }}>
                <Tag style={{ marginRight: 6 }}>{item.field}</Tag>
                <span>{item.value}</span>
              </div>
            ))}
          </div>
        )
        return (
          <Popover content={content} title="变更详情" trigger="hover">
            <span style={{ cursor: 'pointer', color: '#1677ff' }}>{summary}</span>
          </Popover>
        )
      },
    },
    {
      title: '操作', width: 160, align: 'center',
      render: (_, r) => r.status === 'pending' ? (
        <Space>
          <Popconfirm title={`确认通过变更审批？变更将应用到阶段"${r.phase_name}"`} onConfirm={() => handlePhaseApprove(r)}>
            <Button type="primary" size="small">通过</Button>
          </Popconfirm>
          <Button size="small" onClick={() => handlePhaseReject(r)}>拒绝</Button>
        </Space>
      ) : <span style={{ color: '#999', fontSize: 12 }}>{r.review_comment || '-'}</span>,
    },
  ]

  return (
    <Card title="审核中心" extra={<Button onClick={load}>刷新</Button>}>
      <Tabs
        items={[
          {
            key: 'phase-changes',
            label: `阶段变更${phaseChanges.length > 0 ? ` (${phaseChanges.length})` : ''}`,
            children: (
              <Table
                rowKey="id"
                columns={phaseColumns}
                dataSource={phaseChanges}
                loading={loading}
                pagination={false}
                size="middle"
              />
            ),
          },
          ...(userRole === 'admin' ? [{
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
          }] : []),
          ...(userRole === 'admin' ? [{
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
          }] : []),
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

      <Modal
        title="拒绝阶段变更"
        open={!!phaseRejectId}
        onOk={handlePhaseRejectConfirm}
        onCancel={() => { setPhaseRejectId(null); setPhaseRejectComment('') }}
        okText="确认拒绝"
      >
        <p>阶段：{phaseRejectName}</p>
        <Input.TextArea
          placeholder="拒绝原因（可选）"
          rows={3}
          value={phaseRejectComment}
          onChange={(e) => setPhaseRejectComment(e.target.value)}
        />
      </Modal>
    </Card>
  )
}
