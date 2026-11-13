import { useEffect, useState } from 'react'
import { Alert, Card, Col, Row, Segmented, Select, Spin, Statistic, Table, Tag, Tooltip } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'
import {
  getProcessAudit,
  type PlanStabilityRow,
  type ProcessAuditResult,
} from '../api/process_audit'
import { MARKET_OPTION_ITEMS } from '../types'

/**
 * 过程审计（P3 三指标：计划稳定性 / 估算偏差 / 审批时效）。
 * 口径（批档 §2 一）：按字段变更事件计次计天 · 首次计划按字段独立取首值再成对 ·
 * 「批下来」按「决于」读（含驳回件）。防火墙：不设按人维度（不做绩效评分/排名）。
 */
export default function ProcessAuditPage({ embedded }: { embedded?: boolean }) {
  const [data, setData] = useState<ProcessAuditResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [days, setDays] = useState<30 | 90 | 365>(90)
  const [market, setMarket] = useState<string | undefined>()
  const [latencyScope, setLatencyScope] = useState<'decided' | 'approved'>('decided')

  useEffect(() => {
    setLoading(true)
    setError('')
    getProcessAudit({ days, market })
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [days, market])

  const stability = data?.plan_stability ?? []
  const deviations = data?.estimation_deviation ?? []
  const latency = data?.approval_latency

  // 卡片合计 = 明细表逐行可复算（Σ 计次 / Σ 计天；偏差均值只对有值行取）
  const totalChanges = stability.reduce((s, r) => s + r.change_count_project + r.change_count_phase, 0)
  const totalMoveDays = stability.reduce((s, r) => s + r.move_days_total, 0)
  const deviationVals = deviations.map((r) => r.deviation_days).filter((v): v is number => v !== null)
  const deliveryVals = deviations.map((r) => r.delivery_deviation_days)
  const avgDeviation = deviationVals.length
    ? deviationVals.reduce((a, b) => a + b, 0) / deviationVals.length
    : null
  const avgDelivery = deliveryVals.length
    ? deliveryVals.reduce((a, b) => a + b, 0) / deliveryVals.length
    : null

  const stabilityColumns = [
    {
      title: '项目',
      dataIndex: 'project_name',
      key: 'project_name',
      render: (v: string | null, r: PlanStabilityRow) => (
        <span>
          {v ?? '—'}
          {r.project_id === null && <Tag style={{ marginLeft: 6 }}>已删项目</Tag>}
        </span>
      ),
    },
    {
      title: (
        <Tooltip title="按字段变更事件计——一次编辑同改两字段 = 2 次、整体平移按字段各计">
          计划改动次数 <QuestionCircleOutlined style={{ fontSize: 12 }} />
        </Tooltip>
      ),
      children: [
        { title: '项目级', dataIndex: 'change_count_project', key: 'ccp', width: 90 },
        { title: '阶段级', dataIndex: 'change_count_phase', key: 'ccph', width: 90 },
        {
          title: '合计', key: 'cct', width: 90,
          render: (_: unknown, r: PlanStabilityRow) => r.change_count_project + r.change_count_phase,
        },
      ],
    },
    {
      title: '累计挪动天数（天）',
      children: [
        { title: '项目级', dataIndex: 'move_days_project', key: 'mdp', width: 90 },
        { title: '阶段级', dataIndex: 'move_days_phase', key: 'mdph', width: 90 },
        { title: '合计', dataIndex: 'move_days_total', key: 'mdt', width: 90 },
      ],
    },
  ]

  const deviationColumns = [
    { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 160 },
    { title: '阶段', dataIndex: 'phase_name', key: 'phase_name', width: 140 },
    { title: '首次计划开始', dataIndex: 'first_plan_start', key: 'fps', width: 110 },
    { title: '首次计划结束', dataIndex: 'first_plan_end', key: 'fpe', width: 110 },
    { title: '计划工期', dataIndex: 'plan_duration_days', key: 'pd', width: 90 },
    {
      title: '实际开始', dataIndex: 'actual_start', key: 'actual_start', width: 110,
      render: (v: string | null) => v ?? '—',
    },
    { title: '实际结束', dataIndex: 'actual_end', key: 'actual_end', width: 110 },
    {
      title: '实际工期', dataIndex: 'actual_duration_days', key: 'ad', width: 90,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: '工期偏差', dataIndex: 'deviation_days', key: 'dd', width: 90,
      render: (v: number | null) => v ?? '—',
    },
    { title: '交付偏差', dataIndex: 'delivery_deviation_days', key: 'ddd', width: 90 },
  ]

  return (
    /* embedded = 归组进资源负载页 Tab（用户 2026-11-13 功能优化）：去页壳 padding 与页头 */
    <div style={{ padding: embedded ? 0 : 24 }}>
      {!embedded && <h2 style={{ marginBottom: 16 }}>过程审计</h2>}

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          data?.data_start
            ? `数据自 ${data.data_start} 起记录（历史不回填，起点随事件库动态取）`
            : '暂无过程事件数据（自上线日起记录）'
        }
        description="本页为过程数据分析，不做绩效评分/排名，不设按人维度。"
      />

      {/* 筛选：时间窗（与 8-3 趋势图同款交互）+ 市场 */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
        <Segmented
          value={days}
          onChange={(v) => setDays(v as 30 | 90 | 365)}
          options={[
            { label: '30 天', value: 30 },
            { label: '90 天', value: 90 },
            { label: '365 天', value: 365 },
          ]}
        />
        <Select
          style={{ width: 160 }}
          allowClear
          placeholder="全部市场"
          value={market}
          onChange={(v) => setMarket(v)}
          options={MARKET_OPTION_ITEMS}
        />
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        {/* 三指标卡 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <Card
              size="small"
              title={
                <Tooltip title="按字段变更事件计——一次编辑同改两字段 = 2 次、整体平移按字段各计">
                  计划稳定性 <QuestionCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              }
            >
              <Row>
                <Col span={12}><Statistic title="计划改动次数（合计）" value={totalChanges} suffix="次" /></Col>
                <Col span={12}><Statistic title="累计挪动天数（合计）" value={totalMoveDays} suffix="天" /></Col>
              </Row>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary, #999)', marginTop: 8 }}>
                解析失败 {data?.move_parse_skipped ?? 0} 条已显式计数、未计天数（空值/非日期字面）
              </div>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" title="估算偏差（首次计划 vs 实际）">
              <Row>
                <Col span={12}>
                  <Statistic title="平均工期偏差" value={avgDeviation ?? '—'} precision={avgDeviation !== null ? 1 : undefined} suffix={avgDeviation !== null ? '天' : undefined} />
                </Col>
                <Col span={12}>
                  <Statistic title="平均交付偏差" value={avgDelivery ?? '—'} precision={avgDelivery !== null ? 1 : undefined} suffix={avgDelivery !== null ? '天' : undefined} />
                </Col>
              </Row>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary, #999)', marginTop: 8 }}>
                样本 {deviations.length} 阶段（仅已完阶段）· 首次计划缺失 {data?.first_plan_skipped ?? 0} 阶段未计入
              </div>
            </Card>
          </Col>
          <Col span={8}>
            <Card
              size="small"
              title={
                <Tooltip title="「批下来」按「决于」读（含驳回件）；按改期申请「提交→决于」计时，审批事件（source=approval）只作条数对照">
                  审批时效 <QuestionCircleOutlined style={{ fontSize: 12 }} />
                </Tooltip>
              }
              extra={
                <Segmented
                  size="small"
                  value={latencyScope}
                  onChange={(v) => setLatencyScope(v as 'decided' | 'approved')}
                  options={[
                    { label: '已决（含驳回）', value: 'decided' },
                    { label: '仅批准', value: 'approved' },
                  ]}
                />
              }
            >
              <Statistic
                title="平均审批时长"
                value={
                  latencyScope === 'decided'
                    ? latency?.avg_hours ?? '—'
                    : latency?.approved_avg_hours ?? '—'
                }
                precision={
                  (latencyScope === 'decided' ? latency?.avg_hours : latency?.approved_avg_hours) != null ? 1 : undefined
                }
                suffix={
                  (latencyScope === 'decided' ? latency?.avg_hours : latency?.approved_avg_hours) != null ? '小时' : undefined
                }
              />
              <div style={{ fontSize: 12, color: 'var(--text-tertiary, #999)', marginTop: 8 }}>
                {latencyScope === 'decided'
                  ? `已决 ${latency?.count ?? 0} 件（approved + rejected）`
                  : `仅批准 ${latency?.approved_count ?? 0} 件`}
                　·　pending 不计
              </div>
            </Card>
          </Col>
        </Row>

        {/* 明细表：项目行 */}
        <Card
          size="small"
          title="计划稳定性明细（项目行）"
          style={{ marginBottom: 16 }}
        >
          <Table
            rowKey={(r: PlanStabilityRow) => (r.project_id ?? `deleted-${r.project_name}`)}
            columns={stabilityColumns}
            dataSource={stability}
            pagination={false}
            size="small"
            scroll={{ x: 800 }}
            locale={{ emptyText: '窗口内无计划变更事件' }}
          />
        </Card>

        {/* 明细表：阶段行 */}
        <Card size="small" title="估算偏差明细（阶段行）">
          <Table
            rowKey="phase_id"
            columns={deviationColumns}
            dataSource={deviations}
            pagination={false}
            size="small"
            scroll={{ x: 1100 }}
            locale={{ emptyText: '窗口内无已完阶段' }}
          />
          <div style={{ fontSize: 12, color: 'var(--text-tertiary, #999)', marginTop: 8 }}>
            首次计划 = 各字段独立取首值（该字段有事件取最早事件原值；无事件取现值——未改过即首次）再成对；
            成对缺失的阶段不计入并已显式计数。在途阶段不计（口径不可比）。
          </div>
        </Card>
      </Spin>
    </div>
  )
}
