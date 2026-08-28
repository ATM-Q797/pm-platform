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
 * 冲突消除确认弹窗（v2.1：唯一入口 = 资源负载甘特图冲突条）。
 *
 * - 消除粒度 = 资源 × 阶段（甘特条）：该阶段不计入该资源的并行计算
 * - 并行重算：消除后该资源并行数下降，若剩余 ≤3 其冲突对自动消失（无需逐个消除）
 * - 提交成功后回调 onOverridden（全站视图经 conflict-changed 事件同步刷新）
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
      message.success(`已消除 ${target.resourceName} 的「${target.summary}」——该阶段不再计入并行计算`)
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
          消除该甘特条 = 该阶段<b>不计入该人员的并行计算</b>（风险低）。
          消除后该人员并行数下降——若剩余阶段并行 ≤3，其余冲突自动消失；
          仍 &gt;3 的冲突继续显示，直到消除某条把并行数降下来。
          可在「审核中心 → 资源冲突」查看/撤销消除记录。
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
