import { useEffect, useMemo, useState } from 'react'
import {
  Drawer,
  Form,
  Input,
  Select,
  AutoComplete,
  Slider,
  DatePicker,
  Button,
  Space,
  Tag,
  Modal,
  message,
  Divider,
} from 'antd'
import { DeleteOutlined, ReloadOutlined, SaveOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getPhase, updatePhase, createPhase, deletePhase, reworkPhase, listPhases, movePhase, listDependencies, createDependency, deleteDependency } from '../../api/phases'
import { listResources } from '../../api/resources'
import { getProject } from '../../api/projects'
import { createPhaseChangeRequest } from '../../api/audit'
import type { Phase, Resource, Dependency } from '../../types'

interface Props {
  /** 编辑模式：阶段 id；创建模式：null；关闭：undefined */
  phaseId?: number | null
  /** 创建模式时必需：所属项目 id */
  projectId?: number
  /** 默认 sequence（创建模式时自动传入） */
  defaultSequence?: number
  /** 只读模式：仅查看，不显示保存/删除/移动等操作按钮 */
  readonly?: boolean
  /** 当前用户角色（用于审批流程判断） */
  userRole?: string
  /** 精简模式：隐藏顺序调整、依赖等高级字段（资源视图使用） */
  hideExtra?: boolean
  /** 专项项目模式：阶段类型放开自由输入（AutoComplete 联想，SPECIAL_PROJECT §三） */
  specialProject?: boolean
  onClose: () => void
  onSaved: () => void
}

const STATUS_OPTIONS = ['未开始', '进行中', '已完成', '延期', '已搁置'].map((s) => ({ value: s, label: s }))

// 标准阶段类型（PHASE_TYPES_V2 §一：P1-P9 + P71/P72 子编号），含默认显示名称；
// 历史数据旧值兼容见 LEGACY_TYPE_OPTIONS / toDisplayLabel / isLegacyType（决策 ③ 不迁移：
// 旧 P6=样机打样、旧 P7=联调测试、旧 P8=交付——显示不能错挂新语义，保存不能触发改名）
const PHASE_TYPE_OPTIONS = [
  { value: 'P1', label: '需求评估', name: '需求评估' },
  { value: 'P2', label: '配置评估', name: '配置评估' },
  { value: 'P3', label: '模块选型', name: '模块选型' },
  { value: 'P4', label: '工业设计', name: '工业设计' },
  { value: 'P5', label: '结构设计', name: '结构设计' },
  { value: 'P6', label: '线缆设计', name: '线缆设计' },
  { value: 'P71', label: '样机打样', name: '样机打样' },
  { value: 'P72', label: '线缆打样', name: '线缆打样' },
  { value: 'P8', label: '联调测试', name: '联调测试' },
  { value: 'P9', label: '交付', name: '交付' },
]

// 旧编号兼容选项（历史数据原语义显示；与新值并存时用户可辨，不再错显"线缆设计"/裸 P7）
const LEGACY_TYPE_OPTIONS = [
  { value: 'P6', label: '样机打样（旧·原P6）', name: '样机打样' },
  { value: 'P7', label: '联调测试（旧·原P7）', name: '联调测试' },
  { value: 'P8', label: '交付（旧·原P8）', name: '交付' },
]

/** 阶段类型存储值 → 显示 label（甘特条/摘要等纯文本场景用；旧值走旧义，未知原样回显） */
export function toDisplayLabel(phaseType: string | undefined): string | undefined {
  if (!phaseType) return undefined
  const legacy = LEGACY_TYPE_OPTIONS.find((o) => o.value === phaseType)
  if (legacy) return legacy.label
  const std = PHASE_TYPE_OPTIONS.find((o) => o.value === phaseType)
  return std ? std.label : phaseType
}

/** 阶段是否仍持有旧编号类型（保存时不改名，保持历史原样） */
function isLegacyType(phaseType: string): boolean {
  return LEGACY_TYPE_OPTIONS.some((o) => o.value === phaseType)
}

export default function PhaseEditor({ phaseId, projectId, defaultSequence, readonly, userRole, hideExtra, specialProject, onClose, onSaved }: Props) {
  const isCreate = phaseId === null
  const isOpen = phaseId !== undefined && (phaseId !== null || projectId != null)

  const [phase, setPhase] = useState<Phase | null>(null)
  const [resources, setResources] = useState<Resource[]>([])
  const [projectPhases, setProjectPhases] = useState<Phase[]>([])
  const [saving, setSaving] = useState(false)
  const [moving, setMoving] = useState(false)
  const [currentDeps, setCurrentDeps] = useState<Dependency[]>([])
  const [projectInfo, setProjectInfo] = useState<{ name: string; owner: string } | null>(null)
  const [form] = Form.useForm()

  // 阶段类型选项（SPECIAL_PROJECT §三）：专项项目放开自由输入——联想 = 本项目已用类型 + P1-P9 建议（含 P71/P72）
  const phaseTypeOptions = useMemo(() => {
    if (!specialProject) return PHASE_TYPE_OPTIONS
    const used = [...new Set(projectPhases.map((p) => p.phase_type).filter(Boolean))]
    const custom = used
      .filter((t) => !PHASE_TYPE_OPTIONS.some((o) => o.value === t))
      .map((t) => ({ value: t, label: t }))
    return [...PHASE_TYPE_OPTIONS, ...custom]
  }, [specialProject, projectPhases])

  useEffect(() => {
    if (phaseId != null && phaseId > 0) {
      // 编辑模式：加载阶段、资源、项目阶段、依赖
      const loadEdit = async () => {
        const [ph, res, phs, deps] = await Promise.all([
          getPhase(phaseId),
          listResources(),
          projectId ? listPhases(projectId).catch(() => []) : Promise.resolve([]),
          projectId ? listDependencies(projectId).catch(() => []) : Promise.resolve([]),
        ])
        setPhase(ph)
        setResources(res)
        setProjectPhases(phs)
        setCurrentDeps(deps)
        // hideExtra 模式下加载项目信息（资源视图弹窗显示）
        if (hideExtra && ph.project_id) {
          getProject(ph.project_id).then((p) => setProjectInfo({ name: p.name, owner: p.owner })).catch(() => {})
        }
        // 前置依赖：哪些阶段指向我
        const dependsOnIds = deps.filter(d => d.to_phase_id === ph.id).map(d => d.from_phase_id)
        // 后续依赖：我指向哪些阶段
        const dependedByIds = deps.filter(d => d.from_phase_id === ph.id).map(d => d.to_phase_id)
        form.setFieldsValue({
          phase_type: ph.phase_type,
          status: ph.status,
          progress: ph.progress,
          plan_start: ph.plan_start ? dayjs(ph.plan_start) : null,
          plan_end: ph.plan_end ? dayjs(ph.plan_end) : null,
          actual_start: ph.actual_start ? dayjs(ph.actual_start) : null,
          actual_end: ph.actual_end ? dayjs(ph.actual_end) : null,
          assignee_ids: ph.assignees?.map((a) => a.id) || [],
          remark: ph.remark,
          depends_on_phase_ids: dependsOnIds,
          depended_by_phase_ids: dependedByIds,
        })
      }
      loadEdit()
    } else if (isCreate) {
      // 创建模式：空表单 + 加载项目现有阶段（用于依赖选择）
      setPhase(null)
      Promise.all([
        listResources(),
        projectId ? listPhases(projectId).catch(() => [] as Phase[]) : Promise.resolve([] as Phase[]),
      ]).then(([res, phs]) => {
        setResources(res)
        setProjectPhases(phs)
      })
      form.resetFields()
      form.setFieldsValue({
        status: '未开始',
        progress: 0,
        sequence: defaultSequence ?? 1,
        depends_on_phase_ids: [],
        depended_by_phase_ids: [],
      })
    }
  }, [phaseId, isCreate, defaultSequence, form])

  const handleMove = async (direction: 'up' | 'down') => {
    if (!phase) return
    setMoving(true)
    try {
      await movePhase(phase.id, direction)
      message.success(direction === 'up' ? '已上移一层' : '已下移一层')
      onSaved()
    } catch (e) {
      message.error('移动失败：' + (e as Error).message)
    } finally {
      setMoving(false)
    }
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      if (isCreate && projectId) {
        // 创建新阶段：名称从类型推导
        const typeName = PHASE_TYPE_OPTIONS.find((o) => o.value === values.phase_type)?.name || values.phase_type
        await createPhase(projectId, {
          phase_type: values.phase_type,
          name: values.name || typeName,
          sequence: values.sequence ?? (defaultSequence ?? 1),
          depends_on_phase_ids: values.depends_on_phase_ids || [],
          depended_by_phase_ids: values.depended_by_phase_ids || [],
          plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
          plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
          status: values.status || '未开始',
          progress: values.progress ?? 0,
          assignee_ids: values.assignee_ids || [],
          remark: values.remark || null,
        })
        message.success('阶段已添加')
      } else if (phase) {
        // 编辑已有阶段
        const typeName = PHASE_TYPE_OPTIONS.find((o) => o.value === values.phase_type)?.name
        const payload: Record<string, any> = {}
        if (values.phase_type !== undefined) payload.phase_type = values.phase_type
        // 旧编号阶段（决策 ③）：类型未动（仍是旧值）→ 不改名，保持历史名称原样
        if (typeName && !isLegacyType(values.phase_type)) payload.name = typeName
        if (values.status !== undefined) payload.status = values.status
        if (values.progress !== undefined) payload.progress = values.progress
        if (values.plan_start !== undefined) payload.plan_start = values.plan_start?.format('YYYY-MM-DD') || null
        if (values.plan_end !== undefined) payload.plan_end = values.plan_end?.format('YYYY-MM-DD') || null
        if (values.actual_start !== undefined) payload.actual_start = values.actual_start?.format('YYYY-MM-DD') || null
        if (values.actual_end !== undefined) payload.actual_end = values.actual_end?.format('YYYY-MM-DD') || null
        if (values.assignee_ids !== undefined) payload.assignee_ids = values.assignee_ids
        if (values.remark !== undefined) payload.remark = values.remark

        if (userRole === 'engineer') {
          // 工程师走审批流程
          await createPhaseChangeRequest(phase.id, payload)
          message.success('已提交编辑审批，请等待项目负责人审核')
          // 不处理依赖变更（工程师不能改依赖）
        } else {
          // admin/manager 直接保存
          await updatePhase(phase.id, payload)

          // 同步依赖变更（批量执行，收集错误而非静默吞掉）
          const newDependsOn: number[] = values.depends_on_phase_ids || []
          const newDependedBy: number[] = values.depended_by_phase_ids || []
          // 旧的前置依赖（指向我的阶段 id 列表）
          const oldDependsOn = currentDeps.filter(d => d.to_phase_id === phase.id).map(d => d.from_phase_id)
          // 旧的后置依赖（我指向的阶段 id 列表）
          const oldDependedBy = currentDeps.filter(d => d.from_phase_id === phase.id).map(d => d.to_phase_id)

          // 构建所有依赖变更操作
          const depOps: Promise<unknown>[] = []

          // 删除取消的前置依赖
          for (const fromId of oldDependsOn.filter(id => !newDependsOn.includes(id))) {
            const dep = currentDeps.find(d => d.from_phase_id === fromId && d.to_phase_id === phase.id)
            if (dep) depOps.push(deleteDependency(dep.id))
          }
          // 新增的前置依赖
          for (const fromId of newDependsOn.filter(id => !oldDependsOn.includes(id))) {
            depOps.push(createDependency(phase.project_id, { from_phase_id: fromId, to_phase_id: phase.id }))
          }
          // 删除取消的后置依赖
          for (const toId of oldDependedBy.filter(id => !newDependedBy.includes(id))) {
            const dep = currentDeps.find(d => d.from_phase_id === phase.id && d.to_phase_id === toId)
            if (dep) depOps.push(deleteDependency(dep.id))
          }
          // 新增的后置依赖
          for (const toId of newDependedBy.filter(id => !oldDependedBy.includes(id))) {
            depOps.push(createDependency(phase.project_id, { from_phase_id: phase.id, to_phase_id: toId }))
          }

          // 批量执行，收集失败项
          if (depOps.length > 0) {
            const results = await Promise.allSettled(depOps)
            const failures = results.filter(r => r.status === 'rejected') as PromiseRejectedResult[]
            if (failures.length > 0) {
              message.warning(`阶段已保存，但 ${failures.length} 条依赖关系同步失败，请检查`)
            }
          }

          message.success('已保存')
        }
      } // 结束 else if (phase) 块
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
        isCreate ? '添加阶段' : readonly ? (
          <Space>
            <span>查看阶段</span>
            {phase && phase.rework_count > 0 && <Tag color="orange" style={{ color: '#b45309' }}>返工 {phase.rework_count} 次</Tag>}
          </Space>
        ) : (
          <Space>
            <span>编辑阶段</span>
            {phase && phase.rework_count > 0 && <Tag color="orange" style={{ color: '#b45309' }}>返工 {phase.rework_count} 次</Tag>}
          </Space>
        )
      }
      open={isOpen}
      onClose={onClose}
      styles={{ wrapper: { width: 420 } }}
      destroyOnHidden
      footer={
        readonly ? (
          <Button onClick={onClose}>关闭</Button>
        ) : (
        <Space style={{ float: 'right' }}>
          {!isCreate && phase && userRole !== 'engineer' && (
            <>
              <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>删除</Button>
              <Button icon={<ReloadOutlined />} onClick={handleRework}>返工</Button>
            </>
          )}
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            {isCreate ? '添加' : userRole === 'engineer' ? '提交审批' : '保存'}
          </Button>
        </Space>
        )
      }
    >
      <Form form={form} layout="vertical" preserve={false} disabled={readonly}>
        <Form.Item name="phase_type" label="阶段类型" rules={[{ required: true, message: '请选择阶段类型' }]}>
          {specialProject ? (
            // 专项项目：自由输入（联想 = 本项目已用类型 + P1-P9 建议，SPECIAL_PROJECT §三）
            <AutoComplete
              placeholder="可自由输入或从联想中选择"
              options={phaseTypeOptions}
              filterOption={(input, option) => (option?.value ?? '').includes(input)}
              allowClear
            />
          ) : (
            // 普通项目：P1-P9 标准类型下拉；当前值若为旧编号，动态并入旧义选项显示
            // （决策 ③：旧 P6 显示"样机打样（旧·原P6）"而非错显"线缆设计"）
            <Select
              placeholder="请选择标准阶段类型"
              options={(() => {
                const current = form.getFieldValue('phase_type')
                const legacy = LEGACY_TYPE_OPTIONS.find((o) => o.value === current)
                return legacy ? [...PHASE_TYPE_OPTIONS, legacy] : PHASE_TYPE_OPTIONS
              })()}
            />
          )}
        </Form.Item>
        {isCreate ? (
          <Form.Item name="sequence" label="插入位置">
            <Select
              options={(() => {
                const sorted = [...projectPhases].sort((a, b) => a.sequence - b.sequence)
                const opts: { value: number; label: string }[] = [
                  { value: 1, label: '🏁 最前面' },
                ]
                for (const p of sorted) {
                  opts.push({ value: p.sequence + 1, label: `在「${p.name}」之后` })
                }
                return opts
              })()}
            />
          </Form.Item>
        ) : readonly ? (
          hideExtra ? (
            <>
              <Form.Item label="所属项目">
                <span style={{ color: 'var(--text-secondary)' }}>{projectInfo?.name ?? phase?.project_id ?? '—'}</span>
              </Form.Item>
              <Form.Item label="项目负责人">
                <span style={{ color: 'var(--text-secondary)' }}>{projectInfo?.owner ?? '—'}</span>
              </Form.Item>
            </>
          ) : (
            <Form.Item label="顺序">
              <span style={{ color: 'var(--text-secondary)' }}>第 {phase?.sequence} 位</span>
            </Form.Item>
          )
        ) : phase && userRole !== 'engineer' && !hideExtra && (
          <Form.Item label="顺序调整">
            <Space>
              <Button
                icon={<ArrowUpOutlined />}
                loading={moving}
                onClick={() => handleMove('up')}
              >
                上移一层
              </Button>
              <Button
                icon={<ArrowDownOutlined />}
                loading={moving}
                onClick={() => handleMove('down')}
              >
                下移一层
              </Button>
            </Space>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
              当前序号：{phase.sequence}
            </div>
          </Form.Item>
        )}
        {!hideExtra && (
          <Form.Item name="depends_on_phase_ids" label="前置依赖" extra="选本阶段依赖的前置阶段（可选）">
          <Select
            mode="multiple"
            allowClear
            placeholder="不选则无依赖"
            options={projectPhases
              .filter(p => isCreate || p.id !== phaseId)
              .sort((a, b) => a.sequence - b.sequence)
              .map((p) => ({ value: p.id, label: `${p.name}（序:${p.sequence}）` }))}
          />
        </Form.Item>
        )}
        {!hideExtra && (
          <Form.Item name="depended_by_phase_ids" label="后续阶段" extra="选依赖本阶段的后续阶段（可选）">
          <Select
            mode="multiple"
            allowClear
            placeholder="不选则无后续依赖"
            options={projectPhases
              .filter(p => isCreate || p.id !== phaseId)
              .sort((a, b) => a.sequence - b.sequence)
              .map((p) => ({ value: p.id, label: `${p.name}（序:${p.sequence}）` }))}
          />
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
