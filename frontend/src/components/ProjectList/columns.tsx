// 项目列表列定义（2026-11-05 拆分批次从 ProjectListPage 原样搬出：逻辑体不变，只改 import 与回调注入）。
// 列工厂通过回调注入页面侧行为（跳转/关注/编辑/删除），本组件保持纯呈现；
// STATUS_COLOR 详情页另有一份（不含「延期」项），两份暂存——本批不动详情页。
import { Tag, Button, Space, Popconfirm } from 'antd'
import { EditOutlined, DeleteOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { NavigateFunction } from 'react-router-dom'
import type { Project } from '../../types'
import { HealthStatusCell } from './HealthStatusCell'

// 状态 → Tag 颜色（PROJECT_SHELVE §2.1；旧值「已搁置」兼容已移除——2026-08-28）
export const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  搁置: 'warning',
  延期: 'error',
}

export function buildColumns(options: {
  projects: Project[]
  myRole: string
  navigate: NavigateFunction
  toggleFavorite: (r: Project) => void
  handleEdit: (r: Project) => void
  handleDelete: (r: Project) => void
}): ColumnsType<Project> {
  const { projects, myRole, navigate, toggleFavorite, handleEdit, handleDelete } = options
  return [
    {
      title: '★',
      width: 50,
      align: 'center',
      render: (_, r) => (
        <a
          onClick={(e) => { e.stopPropagation(); toggleFavorite(r) }}
          style={{ fontSize: 16, color: r.is_favorite ? '#fadb14' : '#d9d9d9' }}
          title={r.is_favorite ? '取消关注' : '关注'}
        >
          {r.is_favorite ? <StarFilled /> : <StarOutlined />}
        </a>
      ),
    },
    { title: '序号', width: 70, align: 'center', dataIndex: 'sequence_position',
      // 序号 = 项目在全量有序列表中的位置（非当前页序号）：
      // 项目列表页分页、填报页不分页，用全局位置才能两页一致（用户 2026-10-30 指令）
      render: (_: unknown, r: Project, index: number) => {
        const pos = projects.findIndex((p) => p.id === r.id)
        return pos >= 0 ? pos + 1 : index + 1
      } },
    {
      title: '项目名称',
      dataIndex: 'name',
      render: (_, r) => (
        <a onClick={() => navigate(`/projects/${r.id}`)}>{r.name}</a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      align: 'center',
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: '类目', dataIndex: 'category', width: 100, align: 'center' },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      align: 'center',
      render: (m: string) => <Tag color="blue">{m}</Tag>,
    },
    { title: '负责人', dataIndex: 'owner', width: 100 },
    {
      title: '健康度',
      dataIndex: 'health',
      width: 90,
      align: 'center',
      // 8-2 规则灯：色点+主因短语（搁置/专项 health=null → 「—」）；口径唯一来源后端，前端零计算
      render: (_, r) => <HealthStatusCell health={r.health} />,
    },
    { title: '计划开始', dataIndex: 'plan_start', width: 120, align: 'center',
      render: (v: string) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span> },
    { title: '计划结束', dataIndex: 'plan_end', width: 120, align: 'center',
      render: (v: string) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span> },
    // 操作列对观察者整体不显示（用户 2026-11-11 权限分级需求 4：无编辑权限，全部数据只读）
    ...(myRole === 'viewer'
      ? []
      : [{
          title: '操作',
          width: 140,
          align: 'center' as const,
          render: (_: unknown, r: Project) => (
            <Space size="small">
              <Button size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); handleEdit(r) }}>
                编辑
              </Button>
              <Popconfirm
                title={myRole === 'admin' ? `删除项目 "${r.name}"？此操作不可恢复` : `申请删除项目 "${r.name}"？`}
                onConfirm={() => handleDelete(r)}
                okText={myRole === 'admin' ? '删除' : '申请'}
                okType="danger"
                cancelText="取消"
              >
                <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
              </Popconfirm>
            </Space>
          ),
        }] as ColumnsType<Project>),
  ]
}

// 关注视图列：复用主列表列，仅去掉序号列（按 dataIndex 结构化裁剪，不依赖展示文案；
// ColumnGroupType 无 dataIndex，本表全部为普通列，'dataIndex' in c 守卫即可）
export function buildFavoriteColumns(columns: ColumnsType<Project>): ColumnsType<Project> {
  return columns.filter((c) => !('dataIndex' in c) || c.dataIndex !== 'sequence_position')
}
