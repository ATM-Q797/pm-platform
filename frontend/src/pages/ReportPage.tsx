import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Input, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ClearOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { MARKET_OPTION_ITEMS, REPORT_FILTERS_KEY, REPORT_SEARCH_KEY } from '../types'
import type { ReportProjectItem, UserInfo } from '../types'
import { listReportProjects } from '../api/report'
import NewProjectModal from '../components/Report/NewProjectModal'
import PhaseDetailTable from '../components/Report/PhaseDetailTable'
import ApprovalTab from '../components/Report/ApprovalTab'

const { Text } = Typography

const PROJECT_STATUS_COLORS: Record<string, string> = {
  未开始: 'default',
  进行中: 'processing',
  已完成: 'success',
  搁置: 'warning',
}

// 筛选持久化（用户 2026-10-30：与项目列表页同款筛选，逻辑一致）——
// sessionStorage 保存筛选，进出保留；刷新由 App.tsx 统一清除；键名独立不与列表页互串
const _DEFAULT_FILTERS = { status: '', market: '', category: '' }
const _readFilters = (): typeof _DEFAULT_FILTERS => {
  try {
    const raw = sessionStorage.getItem(REPORT_FILTERS_KEY)
    if (!raw) return { ..._DEFAULT_FILTERS }
    const v = JSON.parse(raw)
    return { status: v.status || '', market: v.market || '', category: v.category || '' }
  } catch {
    return { ..._DEFAULT_FILTERS }
  }
}
const _readSearch = (): string => {
  try { return sessionStorage.getItem(REPORT_SEARCH_KEY) || '' } catch { return '' }
}

/** 信息填报页（/report，信息填报一期 §五）：筛选栏 + Tab1 已建项目 + Tab2 我的 + Tab3 待我审批。 */
export default function ReportPage({ user }: { user: UserInfo }) {
  const [projects, setProjects] = useState<ReportProjectItem[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [pendingCount, setPendingCount] = useState(0)
  // 筛选状态（用户 2026-10-30：与项目列表页同款——搜索/状态/市场/类目+重置，sessionStorage 进出保留）
  const [filters, setFiltersState] = useState(_readFilters)
  const updateFilters = (next: typeof _DEFAULT_FILTERS) => {
    setFiltersState(next)
    try { sessionStorage.setItem(REPORT_FILTERS_KEY, JSON.stringify(next)) } catch { /* 存储满/禁用时静默：筛选仍可用，仅不跨页保留 */ }
  }
  const [searchText, setSearchTextState] = useState(_readSearch)
  const updateSearchText = (v: string) => {
    setSearchTextState(v)
    try { sessionStorage.setItem(REPORT_SEARCH_KEY, v) } catch { /* 同上 */ }
  }
  const resetFilters = () => {
    setFiltersState({ ..._DEFAULT_FILTERS })
    setSearchTextState('')
    try {
      sessionStorage.removeItem(REPORT_FILTERS_KEY)
      sessionStorage.removeItem(REPORT_SEARCH_KEY)
    } catch { /* 清不掉也不影响本次重置生效 */ }
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setProjects(await listReportProjects())
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, reloadKey])

  const refresh = () => setReloadKey((k) => k + 1)

  const columns: ColumnsType<ReportProjectItem> = [
    {
      title: '项目编号',
      dataIndex: 'code',
      width: 90,
      render: (v: string, row) => (
        <Space_inline>
          {row.is_mine && <Tag color="blue" style={{ margin: 0 }}>我负责</Tag>}
          {row.involved && !row.is_mine && <Tag color="cyan" style={{ margin: 0 }}>我参与</Tag>}
          <Text copyable={false}>{v}</Text>
        </Space_inline>
      ),
    },
    { title: '项目名称', dataIndex: 'name', width: 360, ellipsis: true },
    { title: '类目', dataIndex: 'category', width: 90 },
    {
      title: '项目负责人',
      dataIndex: 'managed_by_name',
      width: 110,
      render: (v: string | null) => v ?? '—',
    },
    { title: '市场', dataIndex: 'market', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => <Tag color={PROJECT_STATUS_COLORS[v] ?? 'default'}>{v}</Tag>,
    },
    {
      title: '项目进度',
      dataIndex: 'progress',
      width: 90,
      align: 'right',
      render: (v: number | null) => (v === null ? '—' : `${v}%`),
    },
    {
      title: '阶段数',
      dataIndex: 'phase_count',
      width: 70,
      align: 'right',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      ellipsis: true,
      render: (v: string | null) => (
        <Tooltip title={v || undefined}>
          <Text type="secondary">{v || '—'}</Text>
        </Tooltip>
      ),
    },
    {
      // 逾期/即将到期标识（用户 2026-10-30 指令）：行最右侧呼吸闪烁，暖红/暖黄一眼可见
      title: '',
      key: 'alert',
      width: 96,
      align: 'right',
      render: (_: unknown, row) => (
        <Space_inline>
          {row.overdue && <span className="pm-alert-tag pm-alert-overdue">逾期</span>}
          {!row.overdue && row.due_soon && <span className="pm-alert-tag pm-alert-due-soon">即将到期</span>}
        </Space_inline>
      ),
    },
  ]

  // 「我的」版块（用户 2026-10-30 指令）：展示我创建/负责/参与的项目——除项目编号不显示外
  // 其余展示与已建项目一致（"我负责/我参与"标记随之移到项目名称列），按创建日期（id 即创建顺序）排序
  // 筛选（用户 2026-10-30：与项目列表页逻辑一致）——搜索词+状态下拉前端过滤，两个版块共用同一筛选
  const filterItems = (rows: ReportProjectItem[]) => {
    const kw = searchText.trim().toLowerCase()
    return rows.filter(
      (p) =>
        (!kw || p.name.toLowerCase().includes(kw) || p.code.toLowerCase().includes(kw)) &&
        (!filters.status || p.status === filters.status) &&
        (!filters.market || p.market === filters.market) &&
        (!filters.category || p.category === filters.category),
    )
  }
  const myProjects = projects
    .filter((p) => p.is_mine || p.involved)
    .sort((a, b) => a.id - b.id)
  const myColumns: ColumnsType<ReportProjectItem> = columns
    .filter((c) => !('dataIndex' in c && c.dataIndex === 'code'))
    .map((c) =>
      'dataIndex' in c && c.dataIndex === 'name'
        ? {
            ...c,
            render: (v: string, row: ReportProjectItem) => (
              <Space_inline>
                {row.is_mine && <Tag color="blue" style={{ margin: 0 }}>我负责</Tag>}
                {row.involved && !row.is_mine && <Tag color="cyan" style={{ margin: 0 }}>我参与</Tag>}
                <span>{v}</span>
              </Space_inline>
            ),
          }
        : c,
    )

  return (
    <div>
      {/* 筛选栏（用户 2026-10-30：与项目列表页同款、逻辑一致——搜索/状态/市场/类目+重置，进出保留） */}
      <div className="pm-toolbar" style={{ marginBottom: 4 }}>
        <Space size="middle" wrap>
          <Input.Search
            placeholder="搜索项目名称/编号"
            allowClear
            style={{ width: 240 }}
            value={searchText}
            onChange={(e) => updateSearchText(e.target.value)}
          />
          <Select
            placeholder="状态"
            style={{ width: 120 }}
            value={filters.status}
            onChange={(v) => updateFilters({ ...filters, status: v })}
            options={[
              { value: '', label: '全部' },
              { value: '进行中', label: '进行中' },
              { value: '已完成', label: '已完成' },
              { value: '未开始', label: '未开始' },
              { value: '搁置', label: '搁置' },
            ]}
          />
          <Select
            placeholder="市场"
            style={{ width: 120 }}
            value={filters.market}
            onChange={(v) => updateFilters({ ...filters, market: v })}
            options={[{ value: '', label: '全部' }, ...MARKET_OPTION_ITEMS]}
          />
          <Select
            placeholder="类目"
            style={{ width: 120 }}
            value={filters.category}
            onChange={(v) => updateFilters({ ...filters, category: v })}
            options={[
              { value: '', label: '全部' },
              { value: '新需求', label: '新需求' },
              { value: '量产升级', label: '量产升级' },
              { value: '改造', label: '改造' },
            ]}
          />
          <Button icon={<ClearOutlined />} onClick={resetFilters}>重置</Button>
        </Space>
      </div>
      <Tabs
        defaultActiveKey="projects"
        items={[
          {
            key: 'projects',
            label: '已建项目',
            children: (
              <div>
                <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
                  <Text type="secondary">
                    点项目行展开阶段明细；列表按创建日期排序。项目负责人可改项目级字段与阶段计划时间，
                    阶段负责人可填实际进展。
                  </Text>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      className="ant-btn"
                      onClick={() => {
                        load()
                        refresh()
                      }}
                      title="刷新"
                    >
                      <ReloadOutlined />
                    </button>
                    <button className="ant-btn ant-btn-primary" onClick={() => setCreateOpen(true)}>
                      <PlusOutlined /> 新建项目
                    </button>
                  </div>
                </div>
                <Table<ReportProjectItem>
                  rowKey="id"
                  size="middle"
                  loading={loading}
                  columns={columns}
                  dataSource={filterItems(projects)}
                  pagination={false}
                  rowClassName={(row) =>
                    expandedId === row.id ? 'pm-report-row-expanded' : 'pm-report-row'
                  }
                  onRow={(row) => ({
                    onClick: () => setExpandedId(expandedId === row.id ? null : row.id),
                    style: { cursor: 'pointer' },
                  })}
                  expandable={{
                    expandedRowKeys: expandedId === null ? [] : [expandedId],
                    expandedRowRender: (row) => (
                      <PhaseDetailTable projectId={row.id} onChanged={refresh} />
                    ),
                    showExpandColumn: false,
                  }}
                />
              </div>
            ),
          },
          {
            key: 'mine',
            label: '我的',
            children: (
              <div>
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary">
                    我创建、负责或参与的项目（按创建日期排序）。点项目行展开阶段明细。
                  </Text>
                </div>
                <Table<ReportProjectItem>
                  rowKey="id"
                  size="middle"
                  loading={loading}
                  columns={myColumns}
                  dataSource={filterItems(myProjects)}
                  pagination={false}
                  rowClassName={(row) =>
                    expandedId === row.id ? 'pm-report-row-expanded' : 'pm-report-row'
                  }
                  onRow={(row) => ({
                    onClick: () => setExpandedId(expandedId === row.id ? null : row.id),
                    style: { cursor: 'pointer' },
                  })}
                  expandable={{
                    expandedRowKeys: expandedId === null ? [] : [expandedId],
                    expandedRowRender: (row) => (
                      <PhaseDetailTable projectId={row.id} onChanged={refresh} />
                    ),
                    showExpandColumn: false,
                  }}
                />
              </div>
            ),
          },
          {
            key: 'approvals',
            label: (
              <Badge count={pendingCount} size="small" offset={[8, -2]}>
                <span>待我审批</span>
              </Badge>
            ),
            children: (
              <ApprovalTab
                onCountChange={setPendingCount}
                onChanged={refresh}
              />
            ),
          },
        ]}
      />
      <NewProjectModal
        open={createOpen}
        user={user}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          refresh()
        }}
      />
    </div>
  )
}

function Space_inline({ children }: { children: React.ReactNode }) {
  return <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>{children}</span>
}
