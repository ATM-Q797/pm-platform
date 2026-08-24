import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Descriptions, Tag, Button, Space, Segmented, Spin, message, Input, Switch } from 'antd'
import { ArrowLeftOutlined, PlusOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import { getProject, updateProject, setFavorite, getCriticalPath } from '../api/projects'
import { getMe } from '../api/auth'
import type { ProjectDetail } from '../types'
import GanttChart from '../components/Gantt/GanttChart'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'

const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  已搁置: 'warning',
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const projectId = Number(id)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingPhase, setEditingPhase] = useState<number | null | undefined>(undefined)
  const [editingName, setEditingName] = useState(false)
  const [tempName, setTempName] = useState('')
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

  const handleRename = async () => {
    if (!project || !tempName.trim()) {
      setEditingName(false)
      return
    }
    try {
      await updateProject(project.id, { name: tempName.trim() })
      message.success('已更新名称')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
    setEditingName(false)
  }

  if (loading && !project) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  if (!project) {
    return <Card>项目不存在</Card>
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          返回列表
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions
          title={
            editingName ? (
              <Space>
                <Input
                  value={tempName}
                  onChange={(e) => setTempName(e.target.value)}
                  style={{ width: 400 }}
                  autoFocus
                />
                <Button size="small" type="primary" onClick={handleRename}>
                  确定
                </Button>
                <Button size="small" onClick={() => setEditingName(false)}>
                  取消
                </Button>
              </Space>
            ) : (
              <Space>
                <span>#{project.code} {project.name}</span>
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
                <Button size="small" type="link" onClick={() => { setTempName(project.name); setEditingName(true) }}>
                  改名
                </Button>
              </Space>
            )
          }
          column={4}
          size="small"
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
              <span style={{ color: '#999' }}>—</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="关键路径" span={4}>
            {criticalPathNames.length > 0 ? (
              <span>
                {criticalPathNames.map((n, i) => (
                  <span key={i}>
                    <Tag color="red" style={{ marginBottom: 4 }}>{n}</Tag>
                    {i < criticalPathNames.length - 1 && <span style={{ color: '#999' }}>→</span>}
                  </span>
                ))}
              </span>
            ) : (
              <span style={{ color: '#999' }}>（无有效日期阶段，无法计算）</span>
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
        size="small"
        title="甘特图"
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
            <span style={{ fontSize: 13, color: '#666' }}>
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
          />
        )}
        <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
          提示：悬停任务条两端圆形手柄拖到另一条 = 创建依赖连线 ｜ 右键连线删除 ｜ 点击甘特条编辑阶段详情（通过编辑面板修改日期）
        </div>
      </Card>

      <PhaseEditor
        phaseId={editingPhase}
        projectId={projectId}
        defaultSequence={(project?.phases?.length ? Math.max(...project.phases.map(p => p.sequence)) + 1 : 1)}
        userRole={userRole}
        readonly={userRole === 'viewer'}
        onClose={() => setEditingPhase(undefined)}
        onSaved={handlePhaseSaved}
      />
    </div>
  )
}
