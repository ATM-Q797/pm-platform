import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Col, Row, Statistic, Table, Tag, Progress, Empty, Spin, message } from 'antd'
import {
  ProjectOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getDashboardStats } from '../api/dashboard'
import type { DashboardStats, DelayedProject } from '../types'

// 状态 → Tag 颜色（与列表页一致）
const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  已搁置: 'warning',
  延期: 'error',
}

// 状态 → 进度条颜色
const STATUS_PROGRESS_COLOR: Record<string, string> = {
  已完成: '#52c41a',
  进行中: '#1890ff',
  未开始: '#d9d9d9',
  延期: '#ff4d4f',
  已搁置: '#8c8c8c',
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

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

  if (loading && !stats) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  if (!stats) {
    return <Card>暂无数据</Card>
  }

  // 延期预警表格列
  const delayedColumns: ColumnsType<DelayedProject> = [
    { title: '编号', dataIndex: 'code', width: 70, align: 'center' },
    {
      title: '项目名称',
      dataIndex: 'name',
      render: (_, r) => <a onClick={() => navigate(`/projects/${r.id}`)}>{r.name}</a>,
    },
    {
      title: '逾期天数',
      dataIndex: 'overdue_days',
      width: 100,
      align: 'center',
      sorter: (a, b) => a.overdue_days - b.overdue_days,
      defaultSortOrder: 'ascend',
      render: (d: number) => <Tag color="error">{d} 天</Tag>,
    },
    { title: '计划结束', dataIndex: 'plan_end', width: 120, align: 'center' },
    { title: '负责人', dataIndex: 'owner', width: 100 },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      align: 'center',
      render: (m: string) => <Tag color="blue">{m}</Tag>,
    },
  ]

  return (
    <div>
      {/* 顶部统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="项目总数"
              value={stats.total_projects}
              prefix={<ProjectOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="进行中"
              value={stats.active_projects}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="延期预警"
              value={stats.delayed_count}
              prefix={<WarningOutlined />}
              valueStyle={{ color: stats.delayed_count > 0 ? '#ff4d4f' : undefined }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="阶段总数" value={stats.total_phases} prefix={<ReloadOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* 项目状态分布 */}
        <Col span={8}>
          <Card title="项目状态分布" size="small">
            {stats.project_status.map((s) => (
              <div key={s.status} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Tag color={STATUS_COLOR[s.status] || 'default'}>{s.status}</Tag>
                  <span>{s.count} 个</span>
                </div>
                <Progress
                  percent={stats.total_projects ? (s.count / stats.total_projects) * 100 : 0}
                  strokeColor={STATUS_PROGRESS_COLOR[s.status] || '#d9d9d9'}
                  showInfo={false}
                  size="small"
                />
              </div>
            ))}
          </Card>
        </Col>

        {/* 阶段状态分布 */}
        <Col span={8}>
          <Card title="阶段状态分布" size="small">
            {stats.phase_status.map((s) => (
              <div key={s.status} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Tag color={STATUS_COLOR[s.status] || 'default'}>{s.status}</Tag>
                  <span>{s.count} 个</span>
                </div>
                <Progress
                  percent={stats.total_phases ? (s.count / stats.total_phases) * 100 : 0}
                  strokeColor={STATUS_PROGRESS_COLOR[s.status] || '#d9d9d9'}
                  showInfo={false}
                  size="small"
                />
              </div>
            ))}
          </Card>
        </Col>

        {/* 返工统计 */}
        <Col span={8}>
          <Card title="返工统计" size="small">
            <Statistic
              title="返工总次数"
              value={stats.total_rework_count}
              valueStyle={{ color: stats.total_rework_count > 0 ? '#fa8c16' : undefined }}
              style={{ marginBottom: 16 }}
            />
            {stats.rework_phases.length > 0 ? (
              stats.rework_phases.slice(0, 5).map((r) => (
                <div
                  key={r.phase_id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '4px 0',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  <span style={{ fontSize: 13 }}>
                    {r.project_name} · {r.phase_name}
                  </span>
                  <Tag color="orange">{r.rework_count} 次</Tag>
                </div>
              ))
            ) : (
              <Empty description="暂无返工" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* 延期预警列表 */}
      <Card
        title={
          <span>
            延期预警{' '}
            {stats.delayed_count > 0 && <Tag color="error">{stats.delayed_count} 个</Tag>}
          </span>
        }
        size="small"
      >
        {stats.delayed_projects.length > 0 ? (
          <Table
            rowKey="id"
            columns={delayedColumns}
            dataSource={stats.delayed_projects}
            pagination={false}
            size="middle"
            onRow={(r) => ({ onClick: () => navigate(`/projects/${r.id}`), style: { cursor: 'pointer' } })}
          />
        ) : (
          <Empty description="暂无延期项目 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  )
}
