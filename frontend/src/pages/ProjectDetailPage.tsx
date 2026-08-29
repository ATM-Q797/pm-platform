import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Descriptions, Tag, Button, Space, Segmented, Spin, message, Switch, Result } from 'antd'
import { ArrowLeftOutlined, PlusOutlined, StarFilled, StarOutlined, EditOutlined } from '@ant-design/icons'
import { getProject, setFavorite, getCriticalPath } from '../api/projects'
import { getMe } from '../api/auth'
import type { ProjectDetail } from '../types'
import GanttChart from '../components/Gantt/GanttChart'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'
import ProjectEditModal from '../components/ProjectEditModal'

const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  搁置: 'warning',
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const projectId = Number(id)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingPhase, setEditingPhase] = useState<number | null | undefined>(undefined)
  // 用于强制刷新甘特图组件（数据变更后重新加载）
  const [ganttKey, setGanttKey] = useState(0)
  const [favorited, setFavorited] = useState(false)
  // 甘特图时间轴尺度
  const [ganttScale, setGanttScale] = useState<'day' | 'week' | 'month'>('week')
  const [showCritical, setShowCritical] = useState(false) // 关键路径高亮开关
  // 关键路径工期（详情页展示，T3）
  const [criticalDuration, setCriticalDuration] = useState<number | null>(null)
  const [criticalPathNames, setCriticalPathNames] = useState<string[]>([])
  const [userRole, setUserRole] = useState<string>('viewer')
  // 顶部"编辑"弹窗(与项目列表共享同一 ProjectEditModal,免回列表改主状态)
  const [editOpen, setEditOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, favorites, cp] = await Promise.all([
        getProject(projectId),
        fetch('/api/projects/favorites').then((r) => r.json()),
        getCriticalPath(projectId).catch(() => null), // 关键路径计算失败不阻塞页面
      ])
      setProject(data)
      setFavorited((favorites as number[]).includes(data.id))
      setCriticalDuration(cp && cp.total_duration > 0 ? cp.total_duration : null)
      setCriticalPathNames(cp?.path || [])
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  // 加载当前用户角色
  useEffect(() => {
    getMe().then((u) => setUserRole(u.role)).catch(() => {})
  }, [])

  const handlePhaseClick = (phaseId: number) => {
    setEditingPhase(phaseId)
  }

  const handleAddPhase = () => {
    setEditingPhase(null) // null = 创建模式
  }

  const handlePhaseSaved = () => {
    setGanttKey((k) => k + 1)
    load()
  }

  if (loading && !project) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  if (!project) {
    return <Card>项目不存在</Card>
  }

  // 专项项目隔离（SPECIAL_PROJECT §4.2）：非 admin/manager 访问专项详情 → 403 提示
  // （后端已 403，此处提供友好提示）
  if (project.is_special && userRole !== 'admin' && userRole !== 'manager') {
    return (
      <Card>
        <Result
          status="403"
          title="无权访问"
          subTitle="专项项目仅管理员或项目负责人可访问"
          extra={
            <Button type="primary" onClick={() => navigate('/projects')}>
              返回项目列表
            </Button>
          }
        />
      </Card>
    )
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(project.is_special ? '/special-projects' : '/projects')}>
          返回{project.is_special ? '专项列表' : '列表'}
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, md: 3, lg: 4 }}
          labelStyle={{ width: 92, flexShrink: 0 }}
          title={
            <Space wrap>
              <span style={{ fontSize: 16, fontWeight: 600 }}>
                #{project.code} {project.name}
              </span>
              <Tag color={STATUS_COLOR[project.status] || 'default'}>{project.status}</Tag>
              <a
                onClick={() => {
                  const target = !favorited
                  setFavorited(target)
                  setFavorite(project.id, target).catch((e) => {
                    setFavorited(!target)
                    message.error('操作失败：' + (e as Error).message)
                  })
                }}
                style={{ fontSize: 18, color: favorited ? '#fadb14' : '#d9d9d9' }}
                title={favorited ? '取消关注' : '关注（置顶）'}
              >
                {favorited ? <StarFilled /> : <StarOutlined />}
              </a>
              <Button size="small" type="link" icon={<EditOutlined />} onClick={() => setEditOpen(true)}>
                编辑
              </Button>
            </Space>
          }
        >
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[project.status] || 'default'}>{project.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="市场">
            <Tag color="blue">{project.market}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="类目">{project.category}</Descriptions.Item>
          <Descriptions.Item label="负责人">{project.owner}</Descriptions.Item>
          <Descriptions.Item label="计划周期">
            {project.plan_start || '?'} ~ {project.plan_end || '?'}
          </Descriptions.Item>
          <Descriptions.Item label="关键路径工期">
            {criticalDuration !== null ? (
              <span style={{ color: '#ff4d4f', fontWeight: 600 }}>{criticalDuration} 天</span>
            ) : (
              <span style={{ color: 'var(--text-tertiary)' }}>—</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="关键路径" span={4}>
            {criticalPathNames.length > 0 ? (
              <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
                {criticalPathNames.map((n, i) => (
                  <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <Tag color="red" style={{ margin: 0 }}>{n}</Tag>
                    {i < criticalPathNames.length - 1 && <span style={{ color: 'var(--text-tertiary)' }}>→</span>}
                  </span>
                ))}
              </span>
            ) : (
              <span style={{ color: 'var(--text-tertiary)' }}>（无有效日期阶段，无法计算）</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="阶段数">{project.phases?.length || 0}</Descriptions.Item>
          <Descriptions.Item label="依赖数">{project.dependencies?.length || 0}</Descriptions.Item>
          {project.priority && (
            <Descriptions.Item label="优先级">
              <Tag color={project.priority === '高' ? 'red' : project.priority === '中' ? 'orange' : 'default'}>
                {project.priority}
              </Tag>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card
        className="pm-no-blur"
        size="small"
        title={`甘特图 · ${project.phases?.length || 0} 个阶段`}
        extra={
          <Space>
            {(userRole === 'admin' || userRole === 'manager') && (
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={handleAddPhase}>
                添加阶段
              </Button>
            )}
            <Segmented
              options={[
                { label: '日', value: 'day' },
                { label: '周', value: 'week' },
                { label: '月', value: 'month' },
              ]}
              value={ganttScale}
              onChange={(val) => setGanttScale(val as 'day' | 'week' | 'month')}
            />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              关键路径
              <Switch
                size="small"
                style={{ marginLeft: 6 }}
                checked={showCritical}
                onChange={setShowCritical}
              />
            </span>
          </Space>
        }
      >
        {loading ? (
          <Spin style={{ display: 'block', margin: '60px auto' }} />
        ) : (
          <GanttChart
            key={ganttKey}
            projectId={projectId}
            scale={ganttScale}
            showCritical={showCritical}
            onPhaseClick={handlePhaseClick}
            onDepsChanged={() => {
              // 依赖连线增删成功 → 关键路径工期/路径名随依赖刷新（用户 2026-08-28）
              setGanttKey((k) => k + 1)
              load()
            }}
          />
        )}
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
          提示：悬停任务条两端圆形手柄拖到另一条 = 创建依赖连线 ｜ 右键连线删除 ｜ 点击甘特条编辑阶段详情（通过编辑面板修改日期）
        </div>
      </Card>

      <PhaseEditor
        phaseId={editingPhase}
        projectId={projectId}
        defaultSequence={(project?.phases?.length ? Math.max(...project.phases.map(p => p.sequence)) + 1 : 1)}
        userRole={userRole}
        readonly={userRole === 'viewer'}
        specialProject={!!project.is_special}
        onClose={() => setEditingPhase(undefined)}
        onSaved={handlePhaseSaved}
      />

      {/* 项目编辑弹窗(与列表页共享;保存后刷新详情 + 甘特) */}
      {project && (
        <ProjectEditModal
          project={{ ...project, is_special: project.is_special } as ProjectDetail}
          open={editOpen}
          onClose={() => setEditOpen(false)}
          onSaved={() => { setGanttKey((k) => k + 1); load() }}
        />
      )}
    </div>
  )
}
