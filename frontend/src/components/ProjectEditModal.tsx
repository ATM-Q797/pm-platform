import { useState } from 'react'
import { Modal, Form, Input, Select, DatePicker, message } from 'antd'
import dayjs from 'dayjs'
import { updateProject } from '../api/projects'
import { MARKET_OPTION_ITEMS } from '../types'
import type { Project } from '../types'

/**
 * 项目编辑弹窗(共享组件)——常规项目列表与项目详情页共用,字段与保存逻辑一致:
 * 名称/类目/市场/负责人/状态/计划起止/备注(PUT /api/projects/{id} 部分更新;无优先级)。
 */
export default function ProjectEditModal({ project, open, onClose, onSaved }: {
  project: Project | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

  // 打开时回填(与列表页 handleEdit 相同的字段集)
  const handleValues = () => {
    if (open && project) {
      form.setFieldsValue({
        category: project.category,
        name: project.name,
        owner: project.owner,
        market: project.market,
        status: project.status,
        plan_start: project.plan_start ? dayjs(project.plan_start) : null,
        plan_end: project.plan_end ? dayjs(project.plan_end) : null,
        remark: project.remark,
      })
    }
  }

  const handleOk = async () => {
    if (!project) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      await updateProject(project.id, {
        category: values.category,
        name: values.name,
        owner: values.owner,
        market: values.market,
        status: values.status,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
        remark: values.remark,
      })
      message.success('项目信息已更新')
      onClose()
      onSaved()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="编辑项目"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      afterOpenChange={(o) => o && handleValues()}
      confirmLoading={saving}
      width={640}
      okText="保存"
      destroyOnHidden
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16, paddingRight: 8 }} preserve={false}>
        <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
          <Input placeholder="项目全称" />
        </Form.Item>
        <Input.Group compact style={{ display: 'flex' }}>
          <Form.Item name="category" label="类目" style={{ flex: 1 }}>
            <Select
              placeholder="选择类目"
              popupMatchSelectWidth={false}
              getPopupContainer={(trigger) => trigger.parentElement || document.body}
              options={[
                { value: '新需求', label: '新需求' },
                { value: '量产', label: '量产' },
                { value: '定制', label: '定制' },
                { value: '改造', label: '改造' },
              ]}
            />
          </Form.Item>
          <Form.Item name="market" label="市场" style={{ flex: 1 }}>
            <Select
              placeholder="选择市场"
              popupMatchSelectWidth={false}
              getPopupContainer={(trigger) => trigger.parentElement || document.body}
              options={MARKET_OPTION_ITEMS}
            />
          </Form.Item>
        </Input.Group>
        <Form.Item name="owner" label="项目负责人" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Input.Group compact style={{ display: 'flex' }}>
          <Form.Item name="status" label="状态" style={{ flex: 1 }}>
            <Select options={[
              { value: '未开始', label: '未开始' },
              { value: '进行中', label: '进行中' },
              { value: '已完成', label: '已完成' },
              { value: '搁置', label: '搁置' },
            ]} />
          </Form.Item>
        </Input.Group>
        <Input.Group compact style={{ display: 'flex' }}>
          <Form.Item name="plan_start" label="计划开始" style={{ flex: 1 }}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="plan_end" label="计划结束" style={{ flex: 1 }}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Input.Group>
        <Form.Item name="remark" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
