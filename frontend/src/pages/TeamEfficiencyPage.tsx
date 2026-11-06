import { useEffect, useState } from 'react'
import { Card, Table, Tag, Spin, Alert, Row, Col, Statistic } from 'antd'
import { listTeamEfficiency, type TeamEfficiency, type PersonMetrics } from '../api/teamEfficiency'

const windowOptions = [
  { label: '7 天', value: 7 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '365 天', value: 365 },
]

export default function TeamEfficiencyPage() {
  const [data, setData] = useState<TeamEfficiency | null>(null)
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(7)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    listTeamEfficiency(days)
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [days])

  const columns = [
    { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
    {
      title: '岗位', dataIndex: 'role', key: 'role', width: 110,
      render: (v: string | null) => v ? <Tag>{v}</Tag> : '—',
    },
    { title: '在办项目数', dataIndex: 'active_projects', key: 'active_projects', width: 100 },
    { title: '峰值并行', dataIndex: 'peak_parallel', key: 'peak_parallel', width: 90 },
    {
      title: '按期完成率', dataIndex: 'on_time_rate', key: 'on_time_rate', width: 140,
      render: (v: number | null, r: PersonMetrics) => v !== null ? `${(v * 100).toFixed(0)}%（${r.on_time_sample}）` : '—',
    },
    {
      title: '返工率', dataIndex: 'rework_rate', key: 'rework_rate', width: 90,
      render: (v: number | null) => v !== null ? `${(v * 100).toFixed(0)}%` : '—',
    },
    {
      title: '平均阶段周期', dataIndex: 'avg_cycle_days', key: 'avg_cycle_days', width: 110,
      render: (v: number | null) => v !== null ? `${v.toFixed(0)} 天` : '—',
    },
    { title: '在办阶段数', dataIndex: 'active_phases', key: 'active_phases', width: 100 },
  ]

  const summary = data?.summary

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 16 }}>团队效率</h2>

      {/* 固定三件套 */}
      <Alert
        message={`完成日记录率：${summary?.completion_date_record_rate != null ? (summary.completion_date_record_rate * 100).toFixed(1) + '%' : '—'}（${summary?.dated_phases ?? 0}/${summary?.total_phases ?? 0} 阶段有完成日）`}
        description="本页为负荷与流程分析，不构成绩效评价。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      {/* 时间窗切换 */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        {windowOptions.map((o) => (
          <a
            key={o.value}
            onClick={() => setDays(o.value)}
            style={{
              padding: '4px 14px',
              borderRadius: 6,
              border: '1px solid',
              borderColor: days === o.value ? '#1677ff' : '#d9d9d9',
              color: days === o.value ? '#1677ff' : '#666',
              background: days === o.value ? '#e6f4ff' : 'transparent',
            }}
          >
            {o.label}
          </a>
        ))}
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        {/* 六卡 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}><Statistic title="在办项目数（合计）" value={data?.persons.reduce((s, p) => s + p.active_projects, 0) ?? 0} /></Col>
          <Col span={4}><Statistic title="峰值并行（最高）" value={Math.max(0, ...(data?.persons.map(p => p.peak_parallel) ?? [0]))} /></Col>
          <Col span={4}><Statistic title="按期完成率" value={summary?.completion_date_record_rate != null ? (summary.completion_date_record_rate * 100).toFixed(1) + '%' : '—'} /></Col>
          <Col span={4}><Statistic title="返工率（均值）" value={(() => { const rates = data?.persons.filter(p => p.rework_rate != null).map(p => p.rework_rate!) ?? []; return rates.length ? (rates.reduce((a, b) => a + b, 0) / rates.length * 100).toFixed(0) + '%' : '—' })()} /></Col>
          <Col span={4}><Statistic title="平均阶段周期" value={(() => { const vals = data?.persons.filter(p => p.avg_cycle_days != null).map(p => p.avg_cycle_days!) ?? []; return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(0) + ' 天' : '—' })()} /></Col>
          <Col span={4}><Statistic title="岗位数" value={Object.keys(data?.role_load ?? {}).length} /></Col>
        </Row>

        {/* 岗位负荷分布 + 完成率 Top */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title="岗位负荷分布（在办项目数）" size="small">
              {Object.entries(data?.role_load ?? {}).map(([role, count]) => (
                <div key={role} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <Tag>{role}</Tag>
                  <span>{count} 个项目</span>
                </div>
              ))}
              {Object.keys(data?.role_load ?? {}).length === 0 && <div style={{ color: '#999' }}>暂无数据</div>}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="完成率 Top（按环节）" size="small">
              {(data?.rework_top ?? []).map((item, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <Tag color={i < 3 ? 'green' : 'default'}>{item.name}</Tag>
                  <span>{(item.on_time_rate * 100).toFixed(0)}%（{item.on_time_sample}）</span>
                </div>
              ))}
              {(data?.rework_top ?? []).length === 0 && <div style={{ color: '#999' }}>暂无完成阶段</div>}
            </Card>
          </Col>
        </Row>

        {/* 按人表格 */}
        <Table
          rowKey="resource_id"
          columns={columns}
          dataSource={data?.persons ?? []}
          pagination={false}
          size="small"
          scroll={{ x: 900 }}
        />
        <div style={{ textAlign: 'center', color: '#999', fontSize: 12, marginTop: 8 }}>
          默认按姓名排序 · 仅显示有阶段的人员 · 不做排名榜
        </div>
      </Spin>
    </div>
  )
}
