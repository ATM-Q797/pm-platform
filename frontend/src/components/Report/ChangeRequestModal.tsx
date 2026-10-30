import { useEffect, useState } from 'react'
import { DatePicker, Form, Modal, Select, Typography, message } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type { ReportChangeRequestItem, ReportMeta, ReportPhaseRow } from '../../types'
import { createReportChangeRequest } from '../../api/report'

const { Text } = Typography

/** 变更申请弹窗（§四流程 1；用户 2026-10-30 指令：参与者可申请变更字段仅限
 * 阶段负责人、计划开始、计划结束三个——阶段名称/类型/顺序不可变更，从弹窗去除）。
 *
 * 参与者点击修改可申请字段 → 弹窗确认 → 提交审核，审核人为项目负责人；批准后生效。
 */
export default function ChangeRequestModal({
  target,
  meta,
  onClose,
  onSubmitted,
}: {
  target: ReportPhaseRow | null
  meta: ReportMeta | null
  onClose: () => void
  onSubmitted: () => void
}) {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  // 打开时以当前值预填（改哪个填哪个，未动的字段提交时跳过）
  useEffect(() => {
    if (target) {
      form.setFieldsValue({
        plan_start: target.plan_start ? dayjs(target.plan_start) : null,
        plan_end: target.plan_end ? dayjs(target.plan_end) : null,
        assignee_ids: target.assignee_ids,
      })
    }
  }, [target, form])

  const handleOk = async () => {
    if (!target) return
    try {
      const v = await form.validateFields()
      const planStart = (v.plan_start as Dayjs | null) ?? null
      const planEnd = (v.plan_end as Dayjs | null) ?? null
      // 仅提交与现值有差异的字段（未变字段不进提案）
      const payload: Record<string, unknown> = { phase_id: target.id }
      if (planStart) payload.plan_start = planStart.format('YYYY-MM-DD')
      if (planEnd) payload.plan_end = planEnd.format('YYYY-MM-DD')
      if (Array.isArray(v.assignee_ids) && v.assignee_ids.join() !== target.assignee_ids.join()) {
        payload.assignee_ids = v.assignee_ids
      }
      if (Object.keys(payload).length === 1) {
        message.warning('没有变更任何字段')
        return
      }
      setSubmitting(true)
      await createReportChangeRequest(payload as Parameters<typeof createReportChangeRequest>[0])
      message.success('变更申请已提交，待项目负责人审批')
      form.resetFields()
      onSubmitted()
    } catch (e) {
      if ((e as Error).message) message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={`变更申请 — ${target?.name ?? ''}`}
      open={target !== null}
      onCancel={onClose}
      onOk={handleOk}
      okText="提交申请"
      confirmLoading={submitting}
      destroyOnClose
      width={480}
    >
      {target?.has_pending && (
        <Text type="warning" style={{ display: 'block', marginBottom: 12 }}>
          该阶段已有待审批的变更申请，再次提交请先等待审批结果。
        </Text>
      )}
      <Form form={form} layout="vertical">
        <Form.Item name="assignee_ids" label="阶段负责人">
          <Select
            mode="multiple"
            options={(meta?.resources ?? []).map((r) => ({ value: r.id, label: r.name }))}
            placeholder="至少保留一人"
          />
        </Form.Item>
        <Form.Item name="plan_start" label="计划开始">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="plan_end" label="计划结束">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
      </Form>
      <Text type="secondary">
        可申请变更字段仅限阶段负责人与计划时间；提交后阶段数据不变，由项目负责人在「待我审批」中批准后生效；同阶段一次只能有一个待审申请。
      </Text>
    </Modal>
  )
}

/** 审批弹窗数据辅助：格式化提案为展示行（字段中文名映射）。 */
const FIELD_LABELS: Record<string, string> = {
  plan_start: '计划开始',
  plan_end: '计划结束',
  name: '阶段名称',
  phase_type: '阶段类型',
  sequence: '顺序',
  assignee_ids: '阶段负责人',
}

export function describeProposal(item: ReportChangeRequestItem): string {
  return Object.entries(item.proposed)
    .map(([field, p]) => {
      const label = FIELD_LABELS[field] ?? field
      const old = Array.isArray(p.old) ? (p.old as unknown[]).join('、') : (p.old ?? '—')
      const nw = Array.isArray(p.new) ? (p.new as unknown[]).join('、') : (p.new ?? '—')
      return `${label}：${old} → ${nw}`
    })
    .join('；')
}

export function toDayjsOrNull(v: string | null | undefined): Dayjs | null {
  return v ? dayjs(v) : null
}
