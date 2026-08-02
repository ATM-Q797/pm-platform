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
import { DeleteOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getPhase, updatePhase, deletePhase, reworkPhase } from '../../api/phases'
import { listResources } from '../../api/resources'
import type { Phase, Resource } from '../../types'

interface Props {
  phaseId: number | null
  onClose: () => void
  onSaved: () => void // 保存/删除/返工后刷新甘特图
}

const STATUS_OPTIONS = ['未开始', '进行中', '已完成', '延期', '已搁置'].map((s) => ({
  value: s,
  label: s,
}))

export default function PhaseEditor({ phaseId, onClose, onSaved }: Props) {
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase | null>(null)
  const [resources, setResources] = useState<Resource[]>([])
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    if (phaseId != null) {
      setOpen(true)
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
    } else {
      setOpen(false)
      setPhase(null)
    }
  }, [phaseId, form])

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      const payload = {
        name: values.name,
        phase_type: values.phase_type,
        status: values.status,
        progress: values.progress,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
        actual_start: values.actual_start?.format('YYYY-MM-DD') || null,
        actual_end: values.actual_end?.format('YYYY-MM-DD') || null,
        assignee_ids: values.assignee_ids,
        handover_to: values.handover_to || null,
        remark: values.remark || null,
      }
      await updatePhase(phase!.id, payload)
      message.success('已保存')
      onSaved()
      onClose()
    } catch (e) {
      if ((e as any).errorFields) return // 表单校验失败，不提示
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
          <Input.TextArea
            placeholder="返工原因（必填）"
            rows={3}
            onChange={(e) => (reason = e.target.value)}
          />
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
        try {
          await reworkPhase(phase.id, { to_status: '未开始', reason: reason.trim() })
          message.success('已记录返工')
          onSaved()
          onClose()
        } catch (e) {
          message.error('返工失败：' + (e as Error).message)
        }
      },
    })
  }

  const handleDelete = () => {
    if (!phase) return
    Modal.confirm({
      title: '删除阶段',
      content: `确定删除阶段「${phase.name}」？此操作不可恢复，关联的依赖也会一并删除。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deletePhase(phase.id)
          message.success('已删除')
          onSaved()
          onClose()
        } catch (e) {
          message.error('删除失败：' + (e as Error).message)
        }
      },
    })
  }

  return (
    <Drawer
      title={
        phase ? (
          <Space>
            <span>编辑阶段</span>
            {phase.rework_count > 0 && <Tag color="orange">返工 {phase.rework_count} 次</Tag>}
          </Space>
        ) : (
          '编辑阶段'
        )
      }
      open={open}
      onClose={onClose}
      width={420}
      destroyOnClose
      footer={
        <Space style={{ float: 'right' }}>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleRework}>
            返工
          </Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="阶段名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="phase_type" label="阶段类型">
          <Input placeholder="P1-P8（可留空）" />
        </Form.Item>
        <Form.Item name="status" label="状态" rules={[{ required: true }]}>
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
        <Space style={{ display: 'flex' }}>
          <Form.Item name="actual_start" label="实际开始">
            <DatePicker style={{ width: 150 }} />
          </Form.Item>
          <Form.Item name="actual_end" label="实际结束">
            <DatePicker style={{ width: 150 }} />
          </Form.Item>
        </Space>
        <Form.Item name="assignee_ids" label="负责人">
          <Select
            mode="multiple"
            placeholder="选择负责人"
            options={resources.map((r) => ({ value: r.id, label: `${r.name}${r.role ? '（' + r.role + '）' : ''}` }))}
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
