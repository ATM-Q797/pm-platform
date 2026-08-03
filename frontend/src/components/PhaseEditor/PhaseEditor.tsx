import { useEffect, useState } from 'react'
import {
  Drawer,
  Form,
  Input,
  Select,
  Slider,
  DatePicker,
  Button,
  Space,
  Tag,
  Modal,
  message,
  Divider,
} from 'antd'
import { DeleteOutlined, ReloadOutlined, SaveOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getPhase, updatePhase, createPhase, deletePhase, reworkPhase } from '../../api/phases'
import { listResources } from '../../api/resources'
import type { Phase, Resource } from '../../types'

interface Props {
  /** 编辑模式：阶段 id；创建模式：null；关闭：undefined */
  phaseId?: number | null
  /** 创建模式时必需：所属项目 id */
  projectId?: number
  /** 默认 sequence（创建模式时自动传入） */
  defaultSequence?: number
  onClose: () => void
  onSaved: () => void
}

const STATUS_OPTIONS = ['未开始', '进行中', '已完成', '延期', '已搁置'].map((s) => ({ value: s, label: s }))

// 标准阶段类型（PROJECT_SPEC §2.3），含默认显示名称
const PHASE_TYPE_OPTIONS = [
  { value: 'P1', label: 'P1 需求评估', name: '需求评估' },
  { value: 'P2', label: 'P2 配置评估', name: '配置评估' },
  { value: 'P3', label: 'P3 模块选型', name: '模块选型' },
  { value: 'P4', label: 'P4 工业设计', name: '工业设计' },
  { value: 'P5', label: 'P5 结构设计', name: '结构设计' },
  { value: 'P6', label: 'P6 样机打样', name: '样机打样' },
  { value: 'P7', label: 'P7 联调测试', name: '联调测试' },
  { value: 'P8', label: 'P8 交付', name: '交付' },
]

export default function PhaseEditor({ phaseId, projectId, defaultSequence, onClose, onSaved }: Props) {
  const isCreate = phaseId === null
  const isOpen = phaseId !== undefined && (phaseId !== null || projectId != null)

  const [phase, setPhase] = useState<Phase | null>(null)
  const [resources, setResources] = useState<Resource[]>([])
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    if (phaseId != null && phaseId > 0) {
      // 编辑模式
      Promise.all([getPhase(phaseId), listResources()]).then(([ph, res]) => {
        setPhase(ph)
        setResources(res)
        form.setFieldsValue({
          name: ph.name,
          phase_type: ph.phase_type,
          status: ph.status,
          progress: ph.progress,
          plan_start: ph.plan_start ? dayjs(ph.plan_start) : null,
          plan_end: ph.plan_end ? dayjs(ph.plan_end) : null,
          actual_start: ph.actual_start ? dayjs(ph.actual_start) : null,
          actual_end: ph.actual_end ? dayjs(ph.actual_end) : null,
          assignee_ids: ph.assignees?.map((a) => a.id) || [],
          handover_to: ph.handover_to,
          remark: ph.remark,
        })
      })
    } else if (isCreate) {
      // 创建模式：空表单
      setPhase(null)
      listResources().then(setResources)
      form.resetFields()
      form.setFieldsValue({
        status: '未开始',
        progress: 0,
        sequence: defaultSequence ?? 1,
      })
    }
  }, [phaseId, isCreate, defaultSequence, form])

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      if (isCreate && projectId) {
        // 创建新阶段
        await createPhase(projectId, {
          phase_type: values.phase_type || '',
          name: values.name,
          sequence: values.sequence ?? (defaultSequence ?? 1),
          plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
          plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
          status: values.status || '未开始',
          progress: values.progress ?? 0,
          assignee_ids: values.assignee_ids || [],
          handover_to: values.handover_to || null,
          remark: values.remark || null,
        })
        message.success('阶段已添加')
      } else if (phase) {
        // 编辑已有阶段
        const payload: Record<string, any> = {}
        if (values.phase_type !== undefined) payload.phase_type = values.phase_type
        if (values.name !== undefined) payload.name = values.name
        if (values.sequence !== undefined) payload.sequence = values.sequence
        if (values.status !== undefined) payload.status = values.status
        if (values.progress !== undefined) payload.progress = values.progress
        if (values.plan_start !== undefined) payload.plan_start = values.plan_start?.format('YYYY-MM-DD') || null
        if (values.plan_end !== undefined) payload.plan_end = values.plan_end?.format('YYYY-MM-DD') || null
        if (values.actual_start !== undefined) payload.actual_start = values.actual_start?.format('YYYY-MM-DD') || null
        if (values.actual_end !== undefined) payload.actual_end = values.actual_end?.format('YYYY-MM-DD') || null
        if (values.assignee_ids !== undefined) payload.assignee_ids = values.assignee_ids
        if (values.handover_to !== undefined) payload.handover_to = values.handover_to
        if (values.remark !== undefined) payload.remark = values.remark
        await updatePhase(phase.id, payload)
        message.success('已保存')
      }
      onSaved()
      onClose()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error('保存失败：' + (e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleRework = () => {
    if (!phase) return
    let reason = ''
    Modal.confirm({
      title: '阶段返工',
      content: (
        <div style={{ paddingTop: 8 }}>
          <p style={{ marginBottom: 8 }}>将把阶段「{phase.name}」回退到"未开始"状态，并记录返工日志。</p>
          <Input.TextArea placeholder="返工原因（必填）" rows={3} onChange={(e) => (reason = e.target.value)} />
        </div>
      ),
      okText: '确认返工',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        if (!reason.trim()) {
          message.warning('请填写返工原因')
          return Promise.reject()
        }
        await reworkPhase(phase.id, { to_status: '未开始', reason: reason.trim() })
        message.success('已记录返工')
        onSaved()
        onClose()
      },
    })
  }

  const handleDelete = () => {
    if (!phase) return
    Modal.confirm({
      title: '删除阶段',
      content: `确定删除阶段「${phase.name}」？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await deletePhase(phase.id)
        message.success('已删除')
        onSaved()
        onClose()
      },
    })
  }

  if (!isOpen) return null

  return (
    <Drawer
      title={
        isCreate ? '添加阶段' : (
          <Space>
            <span>编辑阶段</span>
            {phase && phase.rework_count > 0 && <Tag color="orange">返工 {phase.rework_count} 次</Tag>}
          </Space>
        )
      }
      open={isOpen}
      onClose={onClose}
      width={420}
      destroyOnClose
      footer={
        <Space style={{ float: 'right' }}>
          {!isCreate && phase && (
            <>
              <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>删除</Button>
              <Button icon={<ReloadOutlined />} onClick={handleRework}>返工</Button>
            </>
          )}
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            {isCreate ? '添加' : '保存'}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item name="name" label="阶段名称" rules={[{ required: true }]}>
          <Input placeholder={isCreate ? '选择类型后自动填充，可修改' : '阶段显示名称'} />
        </Form.Item>
        <Form.Item name="phase_type" label="阶段类型（P1-P8）" rules={[{ required: true, message: '请选择阶段类型' }]}>
          <Select
            placeholder="请选择标准阶段类型"
            options={PHASE_TYPE_OPTIONS}
            onChange={(val) => {
              const opt = PHASE_TYPE_OPTIONS.find((o) => o.value === val)
              if (opt && form.getFieldValue('name') === '') {
                form.setFieldValue('name', opt.name)
              }
            }}
          />
        </Form.Item>
        {isCreate && (
          <Form.Item name="sequence" label="顺序">
            <Input type="number" />
          </Form.Item>
        )}
        <Form.Item name="status" label="状态">
          <Select options={STATUS_OPTIONS} />
        </Form.Item>
        <Form.Item name="progress" label="进度">
          <Slider min={0} max={100} marks={{ 0: '0%', 50: '50%', 100: '100%' }} />
        </Form.Item>
        <Space style={{ display: 'flex' }}>
          <Form.Item name="plan_start" label="计划开始">
            <DatePicker style={{ width: 150 }} />
          </Form.Item>
          <Form.Item name="plan_end" label="计划结束">
            <DatePicker style={{ width: 150 }} />
          </Form.Item>
        </Space>
        {!isCreate && (
          <Space style={{ display: 'flex' }}>
            <Form.Item name="actual_start" label="实际开始">
              <DatePicker style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="actual_end" label="实际结束">
              <DatePicker style={{ width: 150 }} />
            </Form.Item>
          </Space>
        )}
        <Form.Item name="assignee_ids" label="负责人（工程师）">
          <Select
            mode="multiple"
            placeholder="选择负责人"
            options={resources.map((r) => ({ value: r.id, label: r.name + (r.role ? `（${r.role}）` : '') }))}
          />
        </Form.Item>
        <Form.Item name="handover_to" label="交接人">
          <Input />
        </Form.Item>
        <Form.Item name="remark" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
        {phase && phase.rework_count > 0 && (
          <>
            <Divider />
            <div style={{ color: '#fa8c16' }}>
              ⚠ 此阶段已返工 {phase.rework_count} 次，甘特图上以橙色边框标记
            </div>
          </>
        )}
      </Form>
    </Drawer>
  )
}
