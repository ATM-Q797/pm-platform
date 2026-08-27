import { useEffect, useState } from 'react'
import { Button, Input, Modal, Spin, message } from 'antd'
import { createConflictOverride } from '../../api/resources'

export interface OverrideTarget {
  resourceId: number
  resourceName: string
  phaseAId: number
  phaseBId: number
  /** 冲突对摘要（如「A项目·P5结构 × B项目·P5结构 · 重叠 24 天」） */
  summary: string
}

/**
 * 冲突消除确认弹窗（CONFLICT_MODEL_V2 §2.4 三入口共用：热力 Drawer / 甘特冲突条 / 冲突报告）。
 *
 * - 消除粒度 = 资源 × 冲突对：仅消除"这个人这一对"，其他人不受影响
 * - 提交成功后回调 onOverridden（各入口自行刷新 ⚠ / 报告 / 甘特）
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
      message.warning('请填写消除原因（如：并行任务多但工作量小）')
      return
    }
    setSubmitting(true)
    try {
      await createConflictOverride(target.resourceId, {
        phase_a_id: target.phaseAId,
        phase_b_id: target.phaseBId,
        reason: trimmed,
      })
      message.success(`已消除 ${target.resourceName} 的该冲突对 ⚠`)
      onClose()
      onOverridden()
    } catch (e: any) {
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      if (status === 409) message.error('该冲突对已消除，请勿重复操作')
      else if (status === 400) message.error('该对阶段当前对该人员不构成冲突')
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
          消除后：该人员视角下这一对不再报冲突（热力图 ⚠ 消失、格值不变；其他人不受影响）。
          可在冲突报告页「已消除记录」中撤销。
        </div>
        <Input.TextArea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="消除原因（必填），如：并行任务多但工作量小 / 已协调错峰"
          rows={3}
          maxLength={200}
          showCount
          autoFocus
        />
      </Spin>
    </Modal>
  )
}
