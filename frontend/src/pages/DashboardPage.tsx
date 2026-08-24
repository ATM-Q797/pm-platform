import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Col, Row, Statistic, Tag, Empty, Spin, message, Drawer, List } from 'antd'
import {
  ProjectOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  FieldTimeOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { getDashboardStats } from '../api/dashboard'
import { getResourceConflicts } from '../api/resources'
import type { DashboardStats, ResourceConflict } from '../types'

// 明细抽屉类型
type DrawerKey = 'delayed' | 'due' | 'conflict' | 'rework' | null

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  // 明细抽屉
  const [drawerKey, setDrawerKey] = useState<DrawerKey>(null)
  const [conflicts, setConflicts] = useState<ResourceConflict[]>([])
  const [conflictsLoading, setConflictsLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getDashboardStats()
      setStats(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // 打开明细抽屉（冲突数据按需加载）
  const openDrawer = (key: Exclude<DrawerKey, null>) => {
    setDrawerKey(key)
    if (key === 'conflict' && conflicts.length === 0) {
      setConflictsLoading(true)
      getResourceConflicts()
        .then(setConflicts)
        .catch((e) => message.error('冲突明细加载失败：' + (e as Error).message))
        .finally(() => setConflictsLoading(false))
    }
  }

  const drawerTitle: Record<Exclude<DrawerKey, null>, string> = {
    delayed: '延期项目明细（按逾期天数倒序）',
    due: '即将到期明细（未来 7 天）',
    conflict: '资源冲突明细（按重叠天数倒序）',
    rework: '返工阶段明细',
  }

  if (loading && !stats) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  if (!stats) {
    return <Card>暂无数据</Card>
  }

  return (
    <div>
      {/* 6 张统计卡片：2 行 × 3 列 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card hoverable onClick={() => navigate('/projects')} style={{ cursor: 'pointer' }}>
            <Statistic title="项目总数" value={stats.total_projects} prefix={<ProjectOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card hoverable onClick={() => navigate('/projects')} style={{ cursor: 'pointer' }}>
            <Statistic
              title="进行中"
              value={stats.active_projects}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card hoverable onClick={() => openDrawer('delayed')} style={{ cursor: 'pointer' }}>
            <Statistic
              title="延期项目"
              value={stats.delayed_count}
              prefix={<WarningOutlined />}
              valueStyle={{ color: stats.delayed_count > 0 ? '#ff4d4f' : undefined }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card hoverable onClick={() => openDrawer('due')} style={{ cursor: 'pointer' }}>
            <Statistic
              title="即将到期"
              value={stats.due_soon_count}
              prefix={<FieldTimeOutlined />}
              valueStyle={{ color: stats.due_soon_count > 0 ? '#faad14' : undefined }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card hoverable onClick={() => openDrawer('conflict')} style={{ cursor: 'pointer' }}>
            <Statistic
              title="资源冲突"
              value={stats.conflict_count}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: stats.conflict_count > 0 ? '#fa8c16' : undefined }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card hoverable onClick={() => openDrawer('rework')} style={{ cursor: 'pointer' }}>
            <Statistic
              title="返工次数"
              value={stats.total_rework_count}
              prefix={<ToolOutlined />}
              valueStyle={{ color: stats.total_rework_count > 0 ? '#fa8c16' : undefined }}
            />
          </Card>
        </Col>
      </Row>

      {/* 明细抽屉 */}
      <Drawer
        title={drawerKey ? drawerTitle[drawerKey] : ''}
        width={560}
        open={drawerKey !== null}
        onClose={() => setDrawerKey(null)}
      >
        {drawerKey === 'delayed' && (
          <List
            dataSource={stats.delayed_projects}
            locale={{ emptyText: <Empty description="暂无延期项目 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(d) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${d.id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      <Tag color="blue">{d.market}</Tag>
                      {d.name}
                    </span>
                  }
                  description={`负责人：${d.owner || '—'} ｜ 计划结束：${d.plan_end || '—'}`}
                />
                <Tag color="error">逾期 {d.overdue_days} 天</Tag>
              </List.Item>
            )}
          />
        )}

        {drawerKey === 'due' && (
          <List
            dataSource={stats.due_soon_phases}
            locale={{ emptyText: <Empty description="暂无即将到期" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(d) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${d.project_id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {d.project_name} · {d.phase_name}
                    </span>
                  }
                  description={`剩余 ${d.days_left} 天`}
                />
                <Tag color={d.days_left <= 3 ? 'error' : 'warning'}>{d.days_left} 天后到期</Tag>
              </List.Item>
            )}
          />
        )}

        {drawerKey === 'conflict' && (
          <Spin spinning={conflictsLoading}>
            {conflicts.length === 0 && !conflictsLoading ? (
              <Empty description="暂无资源冲突 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              conflicts.map((rc) => (
                <div key={rc.resource_id} style={{ marginBottom: 16 }}>
                  <b style={{ fontSize: 14 }}>{rc.resource_name}</b>
                  <Tag color="orange" style={{ marginLeft: 8 }}>
                    {rc.conflicts.length} 个冲突
                  </Tag>
                  <List
                    dataSource={rc.conflicts}
                    renderItem={(c) => (
                      <List.Item
                        style={{ cursor: 'pointer', padding: '8px 0' }}
                        onClick={() => navigate(`/projects/${c.project_a_id}`)}
                      >
                        <List.Item.Meta
                          title={
                            <span style={{ fontSize: 13 }}>
                              {c.project_a_name}·{c.phase_a_name} × {c.project_b_name}·
                              {c.phase_b_name}
                            </span>
                          }
                        />
                        <Tag color="red">重叠 {c.overlap_days} 天</Tag>
                      </List.Item>
                    )}
                  />
                </div>
              ))
            )}
          </Spin>
        )}

        {drawerKey === 'rework' && (
          <List
            dataSource={stats.rework_phases}
            locale={{ emptyText: <Empty description="暂无返工" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(r) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${r.project_id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {r.project_name} · {r.phase_name}
                    </span>
                  }
                />
                <Tag color="orange">{r.rework_count} 次返工</Tag>
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </div>
  )
}
