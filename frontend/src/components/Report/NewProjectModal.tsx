import { useEffect, useMemo, useState } from 'react'
import {
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Table,
  message,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import type {
  ReportMeta,
  ReportProjectCreatePayload,
  UserInfo,
} from '../../types'
import { createReportProject, getReportMeta } from '../../api/report'

interface PhaseRow {
  key: number
  phase_type: string
  plan_start: Dayjs | null
  plan_end: Dayjs | null
  assignee_ids: number[]
}

/** 新建项目弹窗（§5.1）：编号可留空自动生成 + 三选一类目 + 阶段批量编辑表格。 */
export default function NewProjectModal({
  open,
  user,
  onClose,
  onCreated,
}: {
  open: boolean
  user: UserInfo
  onClose: () => void
  onCreated: () => void
}) {
  const [form] = Form.useForm()
  const [meta, setMeta] = useState<ReportMeta | null>(null)
  const [rows, setRows] = useState<PhaseRow[]>([])
  const [saving, setSaving] = useState(false)
  const [nextKey, setNextKey] = useState(1)

  useEffect(() => {
    if (!open) return
    getReportMeta()
      .then((m) => {
        setMeta(m)
        form.setFieldsValue({
          category: m.categories[0],
          market: m.markets[0],
          status: m.project_statuses[0],
          managed_by: user.id, // §九-2：默认自己是负责人
        })
      })
      .catch((e) => message.error((e as Error).message))
  }, [open, form, user.id])

  // 每次打开重置：10 类阶段预填（§5.1）
  useEffect(() => {
    if (!open || !meta) return
    const initial: PhaseRow[] = meta.phase_types.map((t) => ({
      key: nextKey + Math.random(),
      phase_type: t.value,
      plan_start: null,
      plan_end: null,
      assignee_ids: [],
    }))
    setRows(initial)
    setNextKey((k) => k + initial.length)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, meta])

  const managerOptions = useMemo(
    () => (meta?.users ?? []).map((u) => ({ value: u.id, label: u.name })),
    [meta],
  )
  const assigneeOptions = useMemo(
    () => (meta?.resources ?? []).map((r) => ({ value: r.id, label: r.name })),
    [meta],
  )

  const updateRow = (key: number, patch: Partial<PhaseRow>) => {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      // 行级校验：结束>开始（§5.1）
      for (let i = 0; i < rows.length; i += 1) {
        const r = rows[i]
        if (r.plan_start && r.plan_end && r.plan_end.isBefore(r.plan_start)) {
          message.error(`第 ${i + 1} 行阶段：计划结束不得早于计划开始`)
          return
        }
      }
      const payload: ReportProjectCreatePayload = {
        // 项目编号已停用（用户 2026-10-30 指令）：界面不再提供输入，后端自动生成
        category: values.category,
        name: values.name,
        market: values.market,
        status: values.status,
        remark: values.remark || null,
        managed_by: values.managed_by ?? user.id,
        phases: rows.map((r) => ({
          phase_type: r.phase_type,
          plan_start: r.plan_start ? r.plan_start.format('YYYY-MM-DD') : null,
          plan_end: r.plan_end ? r.plan_end.format('YYYY-MM-DD') : null,
          assignee_ids: r.assignee_ids,
        })),
      }
      setSaving(true)
      const created = await createReportProject(payload)
      message.success(`项目「${created.name}」已创建`)
      form.resetFields()
      onCreated()
    } catch (e) {
      if ((e as Error).message) message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="新建项目"
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      okText="创建"
      confirmLoading={saving}
      width={920}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <Form.Item name="category" label="项目类目" rules={[{ required: true }]}>
            <Select options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} />
          </Form.Item>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请填写项目名称' }]}>
            <Input placeholder="项目名称" maxLength={100} />
          </Form.Item>
          <Form.Item name="managed_by" label="项目负责人" rules={[{ required: true }]}>
            <Select options={managerOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="market" label="市场" rules={[{ required: true }]}>
            <Select options={(meta?.markets ?? []).map((m) => ({ value: m, label: m }))} />
          </Form.Item>
          <Form.Item name="status" label="项目状态" rules={[{ required: true }]}>
            <Select options={(meta?.project_statuses ?? []).map((s) => ({ value: s, label: s }))} />
          </Form.Item>
        </div>
        <Form.Item name="remark" label="项目备注">
          <Input.TextArea rows={2} maxLength={500} placeholder="选填" />
        </Form.Item>
      </Form>

      <div style={{ marginBottom: 8, fontWeight: 600 }}>阶段计划（行序即顺序，可增删行）</div>
      <Table<PhaseRow>
        rowKey="key"
        size="small"
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: '阶段类型',
            width: 150,
            render: (_: unknown, r) => (
              <Select
                size="small"
                style={{ width: '100%' }}
                value={r.phase_type}
                options={(meta?.phase_types ?? []).map((t) => ({ value: t.value, label: t.label }))}
                onChange={(v) => updateRow(r.key, { phase_type: v })}
              />
            ),
          },
          {
            title: '计划开始',
            width: 150,
            render: (_: unknown, r) => (
              <DatePicker
                size="small"
                style={{ width: '100%' }}
                value={r.plan_start ? dayjs(r.plan_start) : null}
                onChange={(d: Dayjs | null) => updateRow(r.key, { plan_start: d })}
              />
            ),
          },
          {
            title: '计划结束',
            width: 150,
            render: (_: unknown, r) => (
              <DatePicker
                size="small"
                style={{ width: '100%' }}
                value={r.plan_end ? dayjs(r.plan_end) : null}
                onChange={(d: Dayjs | null) => updateRow(r.key, { plan_end: d })}
              />
            ),
          },
          {
            title: '阶段负责人（可多选）',
            render: (_: unknown, r) => (
              <Select
                size="small"
                mode="multiple"
                style={{ width: '100%' }}
                placeholder="选人（可空）"
                value={r.assignee_ids}
                options={assigneeOptions}
                onChange={(v: number[]) => updateRow(r.key, { assignee_ids: v })}
                maxTagCount="responsive"
              />
            ),
          },
          {
            title: '',
            width: 80,
            render: (_: unknown, r) => (
              <span style={{ display: 'inline-flex', gap: 4 }}>
                <a
                  onClick={() =>
                    setRows((rs) => {
                      const idx = rs.findIndex((x) => x.key === r.key)
                      const copy = { ...rs[idx], key: nextKey }
                      setNextKey((k) => k + 1)
                      const next = [...rs]
                      next.splice(idx + 1, 0, copy)
                      return next
                    })
                  }
                  title="在下方插入同类型行"
                >
                  <PlusOutlined />
                </a>
                <a
                  onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}
                  title="删除行"
                >
                  <DeleteOutlined />
                </a>
              </span>
            ),
          },
        ]}
        footer={() => (
          <a
            onClick={() => {
              setRows((rs) => [
                ...rs,
                {
                  key: nextKey,
                  phase_type: meta?.phase_types[0]?.value ?? 'P1',
                  plan_start: null,
                  plan_end: null,
                  assignee_ids: [],
                },
              ])
              setNextKey((k) => k + 1)
            }}
          >
            <PlusOutlined /> 添加阶段
          </a>
        )}
      />
    </Modal>
  )
}
