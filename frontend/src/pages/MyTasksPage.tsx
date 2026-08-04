import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Tag, Progress, message, Empty } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import client from '../api/client'
import type { Phase } from '../types'

const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  延期: 'error',
  已搁置: 'warning',
}

interface TaskWithProject extends Phase {
  project_name?: string
  project_code?: string
}

export default function MyTasksPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<TaskWithProject[]>([])
  const [loading, setLoading] = useState(true)
  const [currentUser, setCurrentUser] = useState<{ id: number; name: string; resource_id: number | null } | null>(null)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    setLoading(true)
    try {
      // 获取当前用户
      const { data: me } = await client.get('/auth/me')
      setCurrentUser(me)
      if (!me.resource_id) {
        setTasks([])
        setLoading(false)
        return
      }
      // 获取所有项目，提取分配给当前用户的阶段
      const { data: projects } = await client.get('/projects')
      const myTasks: TaskWithProject[] = []
      for (const p of projects) {
        const { data: phases } = await client.get(`/projects/${p.id}/phases`)
        for (const ph of phases) {
          if (ph.assignees?.some((a: any) => a.id === me.resource_id)) {
            myTasks.push({ ...ph, project_name: p.name, project_code: p.code })
          }
        }
      }
      // 按状态分组排序：进行中 > 未开始 > 已完成
      const order = { '进行中': 0, '延期': 1, '未开始': 2, '已搁置': 3, '已完成': 4 }
      myTasks.sort((a, b) => (order[a.status as keyof typeof order] ?? 9) - (order[b.status as keyof typeof order] ?? 9))
      setTasks(myTasks)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const columns: ColumnsType<TaskWithProject> = [
    {
      title: '状态', dataIndex: 'status', width: 90, align: 'center',
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '项目', dataIndex: 'project_name', width: 200, ellipsis: true,
      render: (_, r) => <a onClick={() => navigate(`/projects/${r.project_id}`)}>{r.project_name}</a>,
    },
    { title: '阶段', dataIndex: 'name', width: 120 },
    {
      title: '进度', dataIndex: 'progress', width: 160,
      render: (p: number) => <Progress percent={p} size="small" />,
    },
    { title: '计划开始', dataIndex: 'plan_start', width: 110, align: 'center' },
    { title: '计划结束', dataIndex: 'plan_end', width: 110, align: 'center' },
    { title: '实际开始', dataIndex: 'actual_start', width: 110, align: 'center' },
    { title: '实际结束', dataIndex: 'actual_end', width: 110, align: 'center' },
  ]

  // 统计
  const stats = {
    total: tasks.length,
    active: tasks.filter(t => t.status === '进行中').length,
    pending: tasks.filter(t => t.status === '未开始').length,
    done: tasks.filter(t => t.status === '已完成').length,
  }

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 32 }}>
          <div><span style={{ fontSize: 24, fontWeight: 600 }}>{stats.total}</span> 总任务</div>
          <div><span style={{ fontSize: 24, fontWeight: 600, color: '#1890ff' }}>{stats.active}</span> 进行中</div>
          <div><span style={{ fontSize: 24, fontWeight: 600, color: '#999' }}>{stats.pending}</span> 未开始</div>
          <div><span style={{ fontSize: 24, fontWeight: 600, color: '#52c41a' }}>{stats.done}</span> 已完成</div>
        </div>
      </Card>

      <Card title={`我的任务（${currentUser?.name || ''}）`} extra="提示：点击项目甘特图中的阶段条可填报进度">
        {tasks.length > 0 ? (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={tasks}
            loading={loading}
            pagination={false}
            size="middle"
          />
        ) : (
          <Empty description={loading ? '加载中...' : '暂无分配给你的任务'} />
        )}
      </Card>
    </div>
  )
}
