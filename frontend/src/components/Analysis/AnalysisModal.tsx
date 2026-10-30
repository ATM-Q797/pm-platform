/** 项目分析弹窗（PROJECT_ANALYSIS §3.3，四板块重构 2026-10-26）。
 *
 * - 顶部 30 天维度 Segmented + 四 Tab（总体盘面 / 交付健康 / 资源负载 / 规模与吞吐）
 *   ——用户 2026-10-26 裁定：统计聚焦项目级，不算阶段完成数
 * - ECharts 按需引入（echarts/core + Line/Bar/Pie + Grid/Tooltip/Legend），动态 import 分包——
 *   不引封装库、不整包引入；模块级单例 Promise 保证只加载一次
 * - 快照不足时显示空态提示；深色/浅色主题均适配
 * - 比率/差分在前端按需计算（后端只存原子计数；weekly.delta 已由后端算好）
 * - 导出 PDF 已移除（用户 2026-10-27 裁定：实际作用不大）
 */
import { useEffect, useRef, useState } from 'react'
import { Button, Empty, Modal, Segmented, Spin, Tabs, message } from 'antd'
import { CloseOutlined, FundOutlined, SyncOutlined } from '@ant-design/icons'
import { getAnalysisTrend, runSnapshot } from '../../api/analysis'
import { useTheme } from '../../theme'
import type { AnalysisMetrics, AnalysisTrend, TrendPoint, WeeklyPoint } from '../../types'
import type { EChartsOption } from 'echarts'
import type { EChartsType } from 'echarts/core'

// ---------- ECharts 按需加载（模块级单例，首次动态 import 后复用） ----------
type EChartsCore = typeof import('echarts/core')
let echartsPromise: Promise<EChartsCore> | null = null
function loadECharts(): Promise<EChartsCore> {
  echartsPromise ??= Promise.all([
    import('echarts/core'),
    import('echarts/charts'),
    import('echarts/components'),
    import('echarts/renderers'),
  ]).then(([core, charts, components, renderers]) => {
    core.use([
      renderers.CanvasRenderer, // 渲染器同为按需注册项，漏注册则 init 报 "Renderer 'undefined'"
      charts.LineChart,
      charts.BarChart,
      charts.PieChart, // 总体盘面：状态/市场分布环图（四板块，2026-10-26）
      components.GridComponent,
      components.TooltipComponent,
      components.LegendComponent,
    ])
    return core
  })
  return echartsPromise
}

// 图表配色与主题适配（canvas 内不能用 CSS 变量，按主题取具体色值）
const PALETTE = ['#1677ff', '#16a34a', '#fa8c16', '#e11d48', '#7b61ff', '#13c2c2']
const AXIS_TEXT: Record<'light' | 'dark', string> = { light: '#555', dark: '#9db0c9' }
const SPLIT_LINE: Record<'light' | 'dark', string> = {
  light: 'rgba(0,0,0,.07)',
  dark: 'rgba(255,255,255,.09)',
}

type SeriesSpec = {
  name: string
  type: 'line' | 'bar'
  data: ([string, number | null])[] // [日期, 值]；null 断线
  yAxisIndex?: 0 | 1
  stack?: string
  area?: boolean
  dashed?: boolean
}

interface TrendChartProps {
  title: string
  xType: 'time' | 'category'
  series: SeriesSpec[]
  pie?: { name: string; data: { name: string; value: number }[] } // 环图模式（给即用，四板块盘面）
  rightAxis?: string // 第二 y 轴名称（给出即启用双轴）
  height?: number
  mode: 'light' | 'dark'
}

function buildOption(p: TrendChartProps): EChartsOption {
  const axisText = AXIS_TEXT[p.mode]
  const splitLine = SPLIT_LINE[p.mode]
  const valueAxis = { type: 'value' as const, axisLabel: { color: axisText } }
  // 环图模式：单容器单环，图例右侧。
  // 外置引导线标签全程启用（用户 2026-10-27 返工：弹窗加宽至 1280 后空间充裕，标签加回）；
  // 图例只留名称不重复数值（数值在标签+tooltip 中）——省横向空间给标签。
  if (p.pie) {
    return {
      backgroundColor: 'transparent',
      color: PALETTE,
      animation: false,
      tooltip: { trigger: 'item', formatter: '{b}: {c}（{d}%）' },
      legend: {
        orient: 'vertical', right: 0, top: 'middle', textStyle: { color: axisText },
      },
      series: [
        {
          name: p.pie.name,
          type: 'pie' as const,
          radius: ['38%', '65%'],
          center: ['38%', '50%'],
          data: p.pie.data,
          label: { color: axisText, formatter: '{b}: {c}' },
          labelLine: { length: 14, length2: 10 }, // 引导线长度收紧，防相邻标签挤压
          emphasis: { focus: 'self' },
        },
      ],
    }
  }
  return {
    backgroundColor: 'transparent',
    color: PALETTE,
    animation: false, // 静态快照数据无需动画（趋势曲线按快照日期离散呈现）
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: axisText } },
    grid: { left: 52, right: p.rightAxis ? 52 : 24, top: 36, bottom: 28 },
    xAxis: {
      type: p.xType,
      axisLabel: { color: axisText },
      splitLine: { show: false },
    },
    yAxis: p.rightAxis
      ? [
          { ...valueAxis, name: '数量', splitLine: { lineStyle: { color: splitLine } } },
          { ...valueAxis, name: p.rightAxis, splitLine: { show: false } },
        ]
      : [{ ...valueAxis, splitLine: { lineStyle: { color: splitLine } } }],
    series: p.series.map((s) => ({
      name: s.name,
      type: s.type,
      data: s.data,
      yAxisIndex: s.yAxisIndex ?? 0,
      stack: s.stack,
      barMaxWidth: 28,
      lineStyle: s.dashed ? { type: 'dashed' } : undefined,
      areaStyle: s.area ? { opacity: 0.25 } : undefined,
      emphasis: { focus: 'series' },
    })),
  }
}

function TrendChart(p: TrendChartProps) {
  const divRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  // 初始化/主题切换：动态加载后 init；暗色用内置 dark 主题
  useEffect(() => {
    let cancelled = false
    loadECharts().then((core) => {
      if (cancelled || !divRef.current) return
      chartRef.current?.dispose()
      const chart = core.init(divRef.current, p.mode === 'dark' ? 'dark' : undefined)
      chart.setOption(buildOption(p))
      chartRef.current = chart
    })
    // 尺寸自适应：窗口缩放 + Tab 切换（隐藏容器宽度 0 → 显示后 resize）
    const ro = new ResizeObserver(() => chartRef.current?.resize())
    if (divRef.current) ro.observe(divRef.current)
    return () => {
      cancelled = true
      ro.disconnect()
      chartRef.current?.dispose()
      chartRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.mode])

  // 数据更新：notMerge 全量替换
  useEffect(() => {
    chartRef.current?.setOption(buildOption(p), true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })

  return (
    <div style={{ border: '1px solid var(--border-color, #eee)', borderRadius: 8, padding: '12px 12px 4px' }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: 'var(--text-primary, #333)' }}>
        {p.title}
      </div>
      <div ref={divRef} style={{ height: p.height ?? 250 }} />
    </div>
  )
}

// ---------- 数据整形 ----------

const STATUS_ORDER = ['未开始', '进行中', '已完成', '搁置'] as const

const dailySeries = (points: TrendPoint[], pick: (m: AnalysisMetrics) => number | null): SeriesSpec['data'] =>
  points.map((pt) => [pt.date, pick(pt.metrics)] as [string, number | null])

// 项目级周差分（用户 2026-10-26 裁定：吞吐聚焦项目级，不算阶段完成数）
const weeklySeries = (points: WeeklyPoint[], key: 'completed_projects_total' | 'shelved_total' | 'started_projects_total'): SeriesSpec['data'] =>
  points.map((w) => [w.week_start, w.delta[key] ?? 0] as [string, number])

// 延期率 = 延期项目数 / 进行中项目数 ×100（分母 0 或缺延期计数 → null 断线）
const delayedRateData = (points: TrendPoint[]): SeriesSpec['data'] =>
  points.map((pt) => {
    const active = pt.metrics.projects_by_status?.['进行中'] ?? 0
    const delayed = pt.metrics.delayed_projects
    return [
      pt.date,
      delayed != null && active > 0 ? Math.round((delayed / active) * 1000) / 10 : null,
    ] as [string, number | null]
  })

// ---------- 主组件 ----------

type RangeDays = 30 // 用户 2026-10-27：以 30 天为准（90/180 维度已删）

interface Props {
  open: boolean
  onClose: () => void
}

export default function AnalysisModal({ open, onClose }: Props) {
  const { mode } = useTheme()
  const [days, setDays] = useState<RangeDays>(30)
  const [trend, setTrend] = useState<AnalysisTrend | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    if (!open) return
    let stale = false
    setLoading(true)
    getAnalysisTrend(days)
      .then((data) => { if (!stale) setTrend(data) })
      .catch((e) => { if (!stale) message.error('趋势数据加载失败：' + (e as Error).message) })
      .finally(() => { if (!stale) setLoading(false) })
    return () => { stale = true }
  }, [open, days])

  const daily = trend?.daily ?? []
  const weekly = trend?.weekly ?? []
  const hasData = daily.length > 0
  const lastDate = daily.length > 0 ? daily[daily.length - 1].date : ''
  const latest = hasData ? daily[daily.length - 1] : null

  // 总体盘面环图数据（取最新快照的分布原子计数）
  const toPieData = (obj: Record<string, number> | undefined) =>
    Object.entries(obj ?? {}).map(([name, value]) => ({ name, value }))
  const statusPie = toPieData(latest?.metrics.projects_by_status)
  const marketPie = toPieData(latest?.metrics.projects_by_market)
  const categoryPie = toPieData(latest?.metrics.projects_by_category)

  const metaLine = hasData
    ? `近 ${days} 天 · 最新快照 ${lastDate} · 共 ${daily.length} 个快照点`
    : '暂无快照数据'

  // 总体盘面指标卡（四板块，取最新快照）
  const cardsBlock = (
    <div key="cards" style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
      {[
        { label: '项目总数', value: latest?.metrics.projects_total },
        { label: '在期项目（未开始+进行中）', value: latest?.metrics.in_flight_projects },
        { label: '活跃人员数', value: latest?.metrics.active_people },
        { label: '资源冲突对数', value: latest?.metrics.conflict_pairs },
      ].map((it) => (
        <div key={it.label}
             style={{ flex: 1, border: '1px solid var(--border-color, #eee)', borderRadius: 8, padding: '10px 12px' }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary, #888)' }}>{it.label}</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary, #333)' }}>
            {loading ? '—' : (it.value ?? '—')}
          </div>
        </div>
      ))}
    </div>
  )

// 名词解释（tooltip 用，用户 2026-10-27：图表术语要有解释）
const GLOSSARY: Record<string, string> = {
  delayed_projects: '延期项目：计划结束日已过仍未完成的项目',
  due_soon_projects: '7天内到期项目：计划结束日在未来 7 天内的在期项目',
  plan_days_too_long: '工期超长：计划工期超过 120 天的项目',
  plan_days_too_short: '工期过短：计划工期不足 7 天的项目',
  delayed_days_p50: 'P50：全部延期项目按逾期天数排序后的中位数——半数延期项目逾期不超过该天数',
  delayed_days_p90: 'P90：逾期天数第 90 百分位——最严重的前 10% 延期项目逾期不超过该天数（反映最坏情况）',
  delayed_rate: '延期率 = 延期项目数 ÷ 进行中项目数 × 100%',
  conflict_pairs: '资源冲突对数：同一时间段被排给同一人的项目任务对数（两人任务重叠计 1 对）',
  peak_parallel_top3_avg: 'TOP3 峰值并行均值：负载最重的 3 个人，同期最多同时压几个任务的平均值',
  active_people: '活跃人员数：近 12 周内有项目任务安排的人数',
}

const chartNote = (keys: string[]) => (
  <div style={{ fontSize: 11, color: 'var(--text-secondary, #999)', margin: '4px 2px 0' }}>
    🛈 {keys.map((k) => GLOSSARY[k]).filter(Boolean).join('；')}
  </div>
)

const tabItems = [
    {
      key: 'overview',
      label: '总体盘面',
      children: (
        <div>
          {cardsBlock}
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <TrendChart mode={mode} xType="time" title="项目状态分布（最新快照）"
                          series={[]} pie={{ name: '项目状态', data: statusPie }} />
            </div>
            <div style={{ flex: 1 }}>
              <TrendChart mode={mode} xType="time" title="市场分布（最新快照）"
                          series={[]} pie={{ name: '市场', data: marketPie }} />
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <TrendChart mode={mode} xType="time" title="类目分布（最新快照）"
                        series={[]} pie={{ name: '类目', data: categoryPie }} />
          </div>
        </div>
      ),
    },
    {
      key: 'health',
      label: '交付健康',
      children: (
        <div>
          <TrendChart
            mode={mode}
            xType="time"
            title="延期项目与即将到期项目趋势"
            series={[
              { name: '延期项目数', type: 'line', data: dailySeries(daily, (m) => m.delayed_projects ?? null) },
              { name: '7 天内到期项目数', type: 'line', data: dailySeries(daily, (m) => m.due_soon_projects ?? null) },
            ]}
          />
          {chartNote(['delayed_projects', 'due_soon_projects'])}
          <div style={{ marginTop: 12 }}>
            <TrendChart
              mode={mode}
              xType="time"
              title="计划工期健康（超长>120天 / 过短<7天）"
              series={[
                { name: '计划工期超长项目数', type: 'bar', data: dailySeries(daily, (m) => m.plan_days_too_long ?? null) },
                { name: '计划工期过短项目数', type: 'bar', data: dailySeries(daily, (m) => m.plan_days_too_short ?? null) },
              ]}
            />
            {chartNote(['plan_days_too_long', 'plan_days_too_short'])}
          </div>
          <div style={{ marginTop: 12 }}>
            <TrendChart
              mode={mode}
              xType="time"
              title="延期深度与延期率"
              rightAxis="延期率 %"
              series={[
                { name: '延期深度 P50（天）', type: 'line', data: dailySeries(daily, (m) => m.delayed_days_p50 ?? null) },
                { name: '延期深度 P90（天）', type: 'line', data: dailySeries(daily, (m) => m.delayed_days_p90 ?? null) },
                { name: '延期率（延期/进行中）', type: 'line', yAxisIndex: 1, dashed: true, data: delayedRateData(daily) },
              ]}
            />
            {chartNote(['delayed_days_p50', 'delayed_days_p90', 'delayed_rate'])}
          </div>
        </div>
      ),
    },
    {
      key: 'resource',
      label: '资源负载',
      children: (
        <div>
          <TrendChart
            mode={mode}
            xType="time"
            title="资源负载趋势"
              series={[
                { name: '资源冲突对数', type: 'line', data: dailySeries(daily, (m) => m.conflict_pairs ?? null) },
                { name: 'TOP3 峰值并行均值', type: 'line', data: dailySeries(daily, (m) => m.peak_parallel_top3_avg ?? null) },
                { name: '活跃人员数', type: 'line', data: dailySeries(daily, (m) => m.active_people ?? null) },
              ]}
            />
            {chartNote(['conflict_pairs', 'peak_parallel_top3_avg', 'active_people'])}
        </div>
      ),
    },
    {
      key: 'scale',
      label: '规模与吞吐',
      children: (
        <div>
          <TrendChart
            mode={mode}
            xType="time"
            title="项目池（按状态堆叠）"
            series={[
              ...STATUS_ORDER.map((s) => ({
                name: s,
                type: 'line' as const,
                stack: 'pool',
                area: true,
                data: dailySeries(daily, (m) => m.projects_by_status?.[s] ?? 0),
              })),
            ]}
          />
          <div style={{ marginTop: 12 }}>
            <TrendChart
              mode={mode}
              xType="category"
              title="每周项目吞吐（新开工 / 完成 / 转搁置）"
              series={[
                { name: '每周新开工项目数', type: 'bar', data: weeklySeries(weekly, 'started_projects_total') },
                { name: '每周完成项目数', type: 'bar', data: weeklySeries(weekly, 'completed_projects_total') },
                { name: '每周转搁置项目数', type: 'bar', data: weeklySeries(weekly, 'shelved_total') },
              ]}
            />
          </div>
        </div>
      ),
    },
  ]

  return (
    <Modal
      title={
        <span>
          <FundOutlined style={{ color: '#1677ff', marginRight: 8 }} />
          项目分析
        </span>
      }
      width={1280}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" icon={<CloseOutlined />} onClick={onClose}>关闭</Button>,
      ]}
    >
      <div style={{ padding: '4px 2px' }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary, #333)' }}>
          项目分析 · {metaLine}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary, #888)', margin: '2px 0 10px' }}>
          专项项目不纳入统计
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 8 }}>
          {/* 数据刷新（用户 2026-10-29 指令）：force 重采当日快照，导入新项目表后立即可见最新分析 */}
          <Button
            icon={<SyncOutlined spin={refreshing} />}
            disabled={refreshing}
            onClick={async () => {
              setRefreshing(true)
              try {
                await runSnapshot(true)
                message.success('分析数据已刷新')
                const data = await getAnalysisTrend(days)
                setTrend(data)
              } catch (e) {
                message.error('刷新失败：' + (e as Error).message)
              } finally {
                setRefreshing(false)
              }
            }}
          >
            数据刷新
          </Button>
          {/* 天数维度仅 30 天（用户 2026-10-27：90/180 切换快照积累有限看不出变化，删除） */}
          <Segmented
            value={days}
            onChange={(v) => setDays(v as RangeDays)}
            options={[{ label: '近 30 天', value: 30 }]}
          />
        </div>
        {loading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : hasData ? (
          <Tabs items={tabItems} />
        ) : (
          <Empty
            style={{ margin: '48px 0' }}
            description="暂无快照数据 — 快照每日自动积累，从上线日起算（部署日可手动触发基线）"
          />
        )}
      </div>
    </Modal>
  )
}
