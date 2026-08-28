import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Col, Row, Tag, Empty, Spin, message, Drawer, List } from 'antd'
import {
  ProjectOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  FieldTimeOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  FireOutlined,
} from '@ant-design/icons'
import { getDashboardStats } from '../api/dashboard'
import { getResourceConflicts } from '../api/resources'
import type { DashboardStats, ResourceConflict } from '../types'

// 明细抽屉类型
type DrawerKey = 'delayed' | 'due' | 'conflict' | 'rework' | null

// 卡片左侧图标块配色（语义色）+ 顶部 3px 渐变条（每卡不同色相，见 tech.css .pm-stat-card）
const CARD_STYLE: Record<string, { bg: string; color: string; bar: string }> = {
  total: { bg: 'rgba(22,119,255,.1)', color: '#1677ff', bar: 'linear-gradient(90deg,#00d4ff,#7b61ff)' },
  active: { bg: 'rgba(34,229,138,.12)', color: '#16a34a', bar: 'linear-gradient(90deg,#22e58a,#00d4ff)' },
  delayed: { bg: 'rgba(255,77,109,.12)', color: '#e11d48', bar: 'linear-gradient(90deg,#ff4d6d,#fa8c16)' },
  due: { bg: 'rgba(251,191,36,.14)', color: '#b45309', bar: 'linear-gradient(90deg,#fbbf24,#fa8c16)' },
  conflict: { bg: 'rgba(250,140,22,.12)', color: '#c2410c', bar: 'linear-gradient(90deg,#fa8c16,#ff4d6d)' },
  rework: { bg: 'rgba(123,97,255,.12)', color: '#6d5ae0', bar: 'linear-gradient(90deg,#7b61ff,#00d4ff)' },
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  // 明细抽屉
  const [drawerKey, setDrawerKey] = useState<DrawerKey>(null)
  const [conflicts, setConflicts] = useState<ResourceConflict[]>([])
  const [conflictsLoading, setConflictsLoading] = useState(false)

  useEffect(() => {
    // 甘特消除后同步刷新本抽屉（用户 2026-08-28 决策 ③：消除统一在甘特，其他视图只同步）
    const onConflictChanged = () => {
      if (drawerKey === 'conflict') {
        setConflictsLoading(true)
        getResourceConflicts().then(setConflicts).catch(() => {}).finally(() => setConflictsLoading(false))
      }
    }
    window.addEventListener('conflict-changed', onConflictChanged)
    return () => window.removeEventListener('conflict-changed', onConflictChanged)
  }, [drawerKey])

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

  // 统计卡片渲染：左侧着色图标块 + 右侧数值
  const renderCard = (
    key: string,
    title: string,
    value: number,
    icon: React.ReactNode,
    onClick: () => void,
    dangerHighlight = false,
  ) => {
    const c = CARD_STYLE[key] || CARD_STYLE.total
    const isDanger = dangerHighlight && value > 0
    return (
      <Col span={8}>
        <Card
          hoverable
          onClick={onClick}
          className="pm-stat-card"
          style={{ cursor: 'pointer', '--stat-bar': c.bar, '--stat-color': c.color } as React.CSSProperties}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 10,
                background: c.bg,
                color: c.color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 22,
                flexShrink: 0,
              }}
            >
              {icon}
            </div>
            <div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 2 }}>{title}</div>
              <div className={isDanger ? 'pm-stat-value pm-stat-danger' : 'pm-stat-value'}>
                {value}
              </div>
            </div>
          </div>
        </Card>
      </Col>
    )
  }

  return (
    <div>
      {/* 6 张统计卡片：2 行 × 3 列，行间大间距 */}
      <Row gutter={16} style={{ marginBottom: 32 }}>
        {renderCard('total', '项目总数', stats.total_projects, <ProjectOutlined />, () => navigate('/projects'))}
        {renderCard('active', '进行中', stats.active_projects, <ClockCircleOutlined />, () => navigate('/projects'))}
        {renderCard('delayed', '延期项目', stats.delayed_count, <WarningOutlined />, () => openDrawer('delayed'), true)}
      </Row>
      <Row gutter={16}>
        {renderCard('due', '即将到期', stats.due_soon_count, <FieldTimeOutlined />, () => openDrawer('due'), true)}
        {renderCard('conflict', '资源冲突', stats.conflict_count, <ThunderboltOutlined />, () => openDrawer('conflict'), true)}
        {renderCard('rework', '返工次数', stats.total_rework_count, <ToolOutlined />, () => openDrawer('rework'), true)}
      </Row>

      {/* 今日聚焦：延期项目 + 即将到期 各前 5 */}
      <Card
        title={
          <span>
            <FireOutlined style={{ color: '#fa8c16', marginRight: 8 }} />
            今日聚焦
          </span>
        }
        className="pm-focus-card"
        style={{ marginTop: 32 }}
      >
        <Row gutter={24}>
          <Col span={12}>
            <div style={{ marginBottom: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
              🔴 延期项目（{stats.delayed_projects.length}）
            </div>
            {stats.delayed_projects.length > 0 ? (
              <List
                size="small"
                dataSource={stats.delayed_projects.slice(0, 5)}
                locale={{ emptyText: <Empty description="暂无" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(d) => (
                  <List.Item
                    style={{ cursor: 'pointer', padding: '6px 0' }}
                    onClick={() => navigate(`/projects/${d.id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{ fontSize: 13 }}>
                          {d.name}
                          <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>{d.market}</Tag>
                        </span>
                      }
                    />
                    <Tag color="error">逾期 {d.overdue_days} 天</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无延期项目 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
              🟡 即将到期（{stats.due_soon_count}）
            </div>
            {stats.due_soon_phases.length > 0 ? (
              <List
                size="small"
                dataSource={stats.due_soon_phases.slice(0, 5)}
                locale={{ emptyText: <Empty description="暂无" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(d) => (
                  <List.Item
                    style={{ cursor: 'pointer', padding: '6px 0' }}
                    onClick={() => navigate(`/projects/${d.project_id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{ fontSize: 13 }}>
                          {d.project_name} · {d.phase_name}
                        </span>
                      }
                    />
                    <Tag color={d.days_left <= 3 ? 'error' : 'warning'}>{d.days_left} 天后到期</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无即将到期" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Col>
        </Row>
      </Card>

      {/* 明细抽屉 */}
      <Drawer
        title={drawerKey ? drawerTitle[drawerKey] : ''}
        width={640}
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
                  <Tag color="orange" style={{ marginLeft: 8, color: '#b45309' }}>
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
                <Tag color="orange" style={{ color: '#b45309' }}>{r.rework_count} 次返工</Tag>
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </div>
  )
}
