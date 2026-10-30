import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  DatePicker,
  Input,
  InputNumber,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import type { ReportMeta, ReportPhaseRow, ReportProjectDetail } from '../../types'
import {
  deleteReportProject,
  getReportMeta,
  getReportProject,
  patchReportPhase,
  patchReportProject,
} from '../../api/report'
import ChangeRequestModal from './ChangeRequestModal'

const STATUS_COLORS: Record<string, string> = {
  未开始: 'default',
  进行中: 'processing',
  已完成: 'success',
  延期: 'error',
  搁置: 'warning',
}

const PHASE_STATUS_OPTIONS = ['未开始', '进行中', '已完成', '延期', '搁置'].map((s) => ({
  value: s,
  label: s,
}))

/**
 * 阶段明细编辑表（§5.2）：字段级可编辑标记由后端下发，前端只按标记渲染禁用态；
 * 权限判定以后端为准——越权 PATCH 会 403 并提示字段名。
 */
export default function PhaseDetailTable({
  projectId,
  onChanged,
}: {
  projectId: number
  onChanged: () => void
}) {
  const [detail, setDetail] = useState<ReportProjectDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [changeTarget, setChangeTarget] = useState<ReportPhaseRow | null>(null)
  const [resourceOptions, setResourceOptions] = useState<{ value: number; label: string }[]>([])
  const [userOptions, setUserOptions] = useState<{ value: number; label: string }[]>([])
  const [meta, setMeta] = useState<ReportMeta | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [d, m] = await Promise.all([getReportProject(projectId), getReportMeta()])
      setDetail(d)
      setMeta(m)
      setResourceOptions(m.resources.map((x) => ({ value: x.id, label: x.name })))
      setUserOptions(m.users.map((x) => ({ value: x.id, label: x.name })))
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const patchPhase = async (row: ReportPhaseRow, patch: Record<string, unknown>) => {
    try {
      const updated = await patchReportPhase(row.id, patch)
      message.success('已保存')
      setDetail((d) =>
        d ? { ...d, phases: d.phases.map((p) => (p.id === row.id ? { ...p, ...updated } : p)) } : d,
      )
      onChanged()
    } catch (e) {
      message.error((e as Error).message)
      load() // 403/校验失败后以服务端值复位
    }
  }

  const patchProject = async (patch: Record<string, unknown>) => {
    try {
      const updated = await patchReportProject(projectId, patch)
      setDetail(updated)
      message.success('已保存')
      onChanged()
    } catch (e) {
      message.error((e as Error).message)
      load()
    }
  }

  if (!detail) {
    return <Table size="small" loading={loading} rowKey="id" columns={[]} dataSource={[]} />
  }

  const pe = detail.editable
  const columns: ColumnsType<ReportPhaseRow> = [
    {
      title: '顺序',
      dataIndex: 'sequence',
      width: 60,
      align: 'center',
      render: (v: number) => <span style={{ color: 'var(--text-secondary)' }}>{v}</span>,
    },
    {
      title: '阶段',
      dataIndex: 'name',
      width: 130,
      render: (v: string, r) => (
        <Space size={4}>
          <Tag style={{ margin: 0 }}>{r.phase_type}</Tag>
          {r.has_pending && <Tag color="orange" style={{ margin: 0 }}>改期待审</Tag>}
          <span>{v}</span>
        </Space>
      ),
    },
    {
      title: '计划开始',
      dataIndex: 'plan_start',
      width: 140,
      render: (v: string | null, r) =>
        r.editable.plan_start ? (
          <DatePicker
            size="small"
            value={v ? dayjs(v) : null}
            onChange={(d: Dayjs | null) =>
              patchPhase(r, { plan_start: d ? d.format('YYYY-MM-DD') : null })
            }
          />
        ) : (
          <TextCell value={v} />
        ),
    },
    {
      title: '计划结束',
      dataIndex: 'plan_end',
      width: 140,
      render: (v: string | null, r) =>
        r.editable.plan_end ? (
          <DatePicker
            size="small"
            value={v ? dayjs(v) : null}
            onChange={(d: Dayjs | null) =>
              patchPhase(r, { plan_end: d ? d.format('YYYY-MM-DD') : null })
            }
          />
        ) : (
          <TextCell value={v} />
        ),
    },
    {
      title: '实际开始',
      dataIndex: 'actual_start',
      width: 140,
      render: (v: string | null, r) =>
        r.editable.actual_start ? (
          <DatePicker
            size="small"
            value={v ? dayjs(v) : null}
            onChange={(d: Dayjs | null) =>
              patchPhase(r, { actual_start: d ? d.format('YYYY-MM-DD') : null })
            }
          />
        ) : (
          <TextCell value={v} />
        ),
    },
    {
      title: '实际结束',
      dataIndex: 'actual_end',
      width: 140,
      render: (v: string | null, r) =>
        r.editable.actual_end ? (
          <DatePicker
            size="small"
            value={v ? dayjs(v) : null}
            onChange={(d: Dayjs | null) =>
              patchPhase(r, { actual_end: d ? d.format('YYYY-MM-DD') : null })
            }
          />
        ) : (
          <TextCell value={v} />
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v: string, r) =>
        r.editable.status ? (
          <Select
            size="small"
            style={{ width: '100%' }}
            value={v}
            options={PHASE_STATUS_OPTIONS}
            onChange={(s) => patchPhase(r, { status: s })}
          />
        ) : (
          <Tag color={STATUS_COLORS[v] ?? 'default'}>{v}</Tag>
        ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 150,
      render: (v: number, r) =>
        r.editable.progress ? (
          <Space size={6}>
            <InputNumber
              size="small"
              min={0}
              max={100}
              value={v}
              onChange={(n) => {
                if (n !== null && n !== v) patchPhase(r, { progress: n })
              }}
              style={{ width: 64 }}
            />
            <Progress percent={v} size="small" style={{ width: 60, marginBottom: 0 }} />
          </Space>
        ) : (
          <Progress percent={v} size="small" style={{ width: 90 }} />
        ),
    },
    {
      title: '阶段负责人',
      dataIndex: 'assignees',
      width: 160,
      render: (_: unknown, r) =>
        detail.is_mine ? (
          <Select
            size="small"
            mode="multiple"
            style={{ width: '100%' }}
            maxTagCount={3}
            maxTagPlaceholder={(omitted) => (
              <Tooltip title={`其余 ${omitted.length} 人：${omitted.map((o) => o.label).join('、')}`}>
                +{omitted.length} …
              </Tooltip>
            )}
            value={r.assignee_ids}
            options={resourceOptions}
            onChange={(ids: number[]) => patchPhase(r, { assignee_ids: ids })}
            placeholder="选择人员"
          />
        ) : (
          <span>{r.assignees.map((a) => a.name).join('、') || '—'}</span>
        ),
    },
    {
      title: '备注',
      dataIndex: 'remark',
      render: (v: string | null, r) =>
        r.editable.remark ? (
          <Input
            size="small"
            defaultValue={v ?? ''}
            placeholder="选填"
            onBlur={(e) => {
              const val = e.target.value || null
              if (val !== v) patchPhase(r, { remark: val })
            }}
          />
        ) : (
          <span style={{ color: 'var(--text-secondary)' }}>{v || '—'}</span>
        ),
    },
    {
      title: '变更申请',
      key: 'change',
      width: 90,
      render: (_: unknown, r) =>
        r.can_request_change && !detail.is_mine ? (
          <a onClick={() => setChangeTarget(r)}>
            {r.has_pending ? '查看待审' : '申请变更'}
          </a>
        ) : null,
    },
  ]

  // 删除项目（用户 2026-10-29 需求 3）：仅项目负责人及管理员；不可恢复
  const handleDelete = async () => {
    try {
      await deleteReportProject(projectId)
      message.success('项目已删除（不可恢复）')
      onChanged()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div>
      {/* 项目级字段行（§3.2：仅项目负责人可改） */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 10,
          padding: '8px 10px',
          background: 'var(--bg-secondary)',
          borderRadius: 6,
          alignItems: 'center',
        }}
      >
        <span>
          类目：
          {pe.category ? (
            <CategorySelect value={detail.category} onChange={(c) => patchProject({ category: c })} />
          ) : (
            detail.category
          )}
        </span>
        <span>
          名称：
          {pe.name ? (
            <NameInput value={detail.name} onSave={(n) => patchProject({ name: n })} />
          ) : (
            detail.name
          )}
        </span>
        <span>
          市场：
          {pe.market ? (
            <MarketSelect value={detail.market} onChange={(m) => patchProject({ market: m })} />
          ) : (
            detail.market
          )}
        </span>
        <span>
          状态：
          {pe.status ? (
            <StatusSelect value={detail.status} onChange={(s) => patchProject({ status: s })} />
          ) : (
            <Tag color={detail.status === '已完成' ? 'success' : detail.status === '搁置' ? 'warning' : 'processing'}>
              {detail.status}
            </Tag>
          )}
        </span>
        <span>
          负责人：
          {pe.managed_by ? (
            <OwnerSelect
              value={detail.managed_by}
              users={userOptions}
              onChange={(id) => patchProject({ managed_by: id })}
            />
          ) : (
            detail.managed_by_name ?? detail.owner ?? '—'
          )}
        </span>
        <span style={{ flex: 1, minWidth: 200 }}>
          备注：
          {pe.remark ? (
            <NameInput value={detail.remark ?? ''} onSave={(r) => patchProject({ remark: r })} placeholder="选填" />
          ) : (
            detail.remark || '—'
          )}
        </span>
        {/* 删除项目（用户 2026-10-29 需求 3）：主行备注右侧；仅项目负责人及管理员；不可恢复 */}
        {detail.can_delete && (
          <Popconfirm
            title={`删除项目「${detail.name}」？`}
            description="删除后不可恢复，名下阶段与审批记录一并清除（操作日志保留）"
            okText="确认删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={handleDelete}
          >
            <Button danger size="small" icon={<DeleteOutlined />}>
              删除项目
            </Button>
          </Popconfirm>
        )}
      </div>

      <Table<ReportPhaseRow>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={detail.phases}
        pagination={false}
      />

      <ChangeRequestModal
        target={changeTarget}
        meta={meta}
        onClose={() => setChangeTarget(null)}
        onSubmitted={() => {
          setChangeTarget(null)
          load()
          onChanged()
        }}
      />
    </div>
  )
}

function TextCell({ value }: { value: string | null }) {
  return <span style={{ color: 'var(--text-secondary)' }}>{value || '—'}</span>
}

function CategorySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select
      size="small"
      style={{ width: 100 }}
      value={value}
      onChange={onChange}
      options={['新需求', '量产升级', '改造'].map((c) => ({ value: c, label: c }))}
    />
  )
}

function MarketSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const MARKETS = [
    '拉美区', '西欧区', '东欧区', '中东区', '亚太区',
    '土耳其区', '非洲区', '北美区', 'OEM业务部', '海外通用',
  ]
  return (
    <Select
      size="small"
      style={{ width: 110 }}
      value={value}
      onChange={onChange}
      options={MARKETS.map((m) => ({ value: m, label: m }))}
    />
  )
}

function StatusSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select
      size="small"
      style={{ width: 100 }}
      value={value}
      onChange={onChange}
      options={['未开始', '进行中', '已完成', '搁置'].map((s) => ({ value: s, label: s }))}
    />
  )
}

function OwnerSelect({
  value,
  users,
  onChange,
}: {
  value: number | null | undefined
  users: { value: number; label: string }[]
  onChange: (v: number) => void
}) {
  // 无匹配选项（负责人已停用等）时显示占位名，避免裸数字 id；value 为空时不注入兜底项
  const matched = users.find((u) => u.value === value)
  const options =
    matched || value == null ? users : [...users, { value: value as number, label: `用户#${value}` }]
  return (
    <Select
      size="small"
      style={{ width: 120 }}
      value={value ?? undefined}
      placeholder="选负责人"
      onChange={onChange}
      showSearch
      optionFilterProp="label"
      options={options}
    />
  )
}

function NameInput({
  value,
  onSave,
  placeholder,
}: {
  value: string
  onSave: (v: string) => void
  placeholder?: string
}) {
  return (
    <Input
      size="small"
      style={{ width: 200 }}
      defaultValue={value}
      placeholder={placeholder}
      onBlur={(e) => {
        const v = e.target.value.trim()
        if (v && v !== value) onSave(v)
      }}
    />
  )
}
