import { useEffect, useState } from 'react'
import { Button, Input, Modal, Spin, message } from 'antd'
import { createConflictOverride } from '../../api/resources'

export interface OverrideTarget {
  resourceId: number
  resourceName: string
  phaseId: number
  /** 阶段摘要（如「A项目·P5结构设计」） */
  summary: string
}

/**
 * 冲突消除确认弹窗（v2.2：唯一入口 = 资源负载甘特图冲突条）。
 *
 * - 消除 = 管理者确认该并行不影响实际负荷：该阶段**不再触发该资源的冲突警告**
 *   （并行判定豁免），但**热力图仍显示实际并行数**（负载照旧，用户 2026-08-28）
 * - 撤销：审核中心 → 资源冲突 → 已消除记录
 * - 错误语义：409 已消除 / 400 当前不构成冲突 / 403 无权限 → message.error 提示
 */
export default function ConflictOverrideModal({
  target,
  open,
  onClose,
  onOverridden,
  onViewPhase,
}: {
  target: OverrideTarget | null
  open: boolean
  onClose: () => void
  onOverridden: () => void
  /** 「查看阶段」次级入口（决策 2，甘特冲突条入口提供；不传则不显示） */
  onViewPhase?: () => void
}) {
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 打开时重置输入
  useEffect(() => {
    if (open) setReason('')
  }, [open, target])

  const handleSubmit = async () => {
    if (!target) return
    const trimmed = reason.trim()
    if (!trimmed) {
      message.warning('请填写消除原因（如：该阶段风险低/工作量小）')
      return
    }
    setSubmitting(true)
    try {
      await createConflictOverride(target.resourceId, {
        phase_id: target.phaseId,
        reason: trimmed,
      })
      message.success(`已确认 ${target.resourceName} 的「${target.summary}」可承受——冲突警告已消除（热力图仍显示实际并行数）`)
      onClose()
      onOverridden()
    } catch (e: any) {
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      if (status === 409) message.error('该阶段已消除，请勿重复操作')
      else if (status === 400) message.error('该阶段当前对该人员不构成冲突')
      else if (status === 403) message.error('无权消除（仅管理员或本项目负责人）')
      else message.error(detail || '消除失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title="消除冲突"
      okText="消除"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={handleSubmit}
      onCancel={onClose}
      destroyOnClose
      width={460}
    >
      <Spin spinning={submitting}>
        <div className="co-summary">{target?.summary}</div>
        {onViewPhase && (
          <Button type="link" size="small" style={{ padding: 0, marginBottom: 8 }} onClick={onViewPhase}>
            查看阶段详情
          </Button>
        )}
        <div className="co-hint">
          消除该甘特条 = <b>确认该并行不影响此人的实际工作负荷</b>（负载均衡说明）。
          消除后：该阶段不再触发冲突警告（并行判定豁免），但<b>热力图仍显示实际并行数</b>，
          便于持续观察真实负载。可在「审核中心 → 资源冲突」查看/撤销。
        </div>
        <Input.TextArea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="消除原因（必填），如：该阶段风险低 / 工作量小 / 已协调错峰"
          rows={3}
          maxLength={200}
          showCount
          autoFocus
        />
      </Spin>
    </Modal>
  )
}
