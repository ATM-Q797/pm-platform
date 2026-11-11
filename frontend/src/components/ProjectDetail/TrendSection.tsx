/** 进度趋势区（8-3 按项目维度的历史趋势，PHASE8_PLAN §三；批次档 项目趋势-2026-11-10 §2 设计点 5）。
 *
 * - 交互形态（用户 2026-11-11 裁定「下拉菜单式，点击即展开整个趋势卡，版面简洁」）：
 *   Collapse 折叠面板默认收起——收起时零请求零图表；每次展开重新拉取（拿最新数据）
 * - 两条线：计划累计完成度 vs 实际累计完成度（缺口即偏差）；四键 metrics 随快照定格
 * - 三类事件点渲染：延期红 / 冲突橙 / 计划变更蓝，hover 显明细
 * - 时间窗 30/90/365 切换（§3.4 时间窗三档）
 * - 数据 <7 天显示「数据积累中（尚需 N 天）」（§七 对策）；无任何快照显示「数据积累中」空态
 * - 缺失日期断开不补零（§3.5 验收②：点位只来自真实快照，ECharts connectNulls=false）
 * - 搁置项目 frozen=true：正常渲染冻结前历史 + 冻结标注（读口径：搁置显冻结前历史）
 * - 专项项目：端点 403 → 面板整体隐藏（与本页健康度区块同模式）
 * - ECharts 按需引入（AnalysisModal 同款动态 import 单例，不引封装库）
 */
import { useEffect, useRef, useState } from 'react'
import { Card, Collapse, Segmented, Spin } from 'antd'
import { getProjectTrend } from '../../api/projects'
import { useTheme } from '../../theme'
import type { ProjectTrend, ProjectTrendEvent } from '../../types'
import type { EChartsOption } from 'echarts'
import type { EChartsType } from 'echarts/core'

// ECharts 按需加载（模块级单例 Promise，与 AnalysisModal 同款——两处独立加载互不干扰）
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
      renderers.CanvasRenderer, // 漏注册则 init 报 "Renderer 'undefined'"
      charts.LineChart,
      charts.ScatterChart, // 事件点
      components.GridComponent,
      components.TooltipComponent,
      components.LegendComponent,
    ])
    return core
  })
  return echartsPromise
}

const AXIS_TEXT: Record<'light' | 'dark', string> = { light: '#555', dark: '#9db0c9' }
const SPLIT_LINE: Record<'light' | 'dark', string> = {
  light: 'rgba(0,0,0,.07)',
  dark: 'rgba(255,255,255,.09)',
}
// 事件点配色（§2 设计点 5：延期红 / 冲突橙 / 计划变更蓝）
const EVENT_COLOR: Record<ProjectTrendEvent['kind'], string> = {
  delayed: '#ff4d4f',
  conflict: '#fa8c16',
  plan_change: '#1677ff',
}

// 数据 <7 天 → 「数据积累中（尚需 N 天）」（§七：历史从上线日积累，不等数据齐才上线）
const ACCUMULATING_TARGET_DAYS = 7

interface Props {
  projectId: number
}

export default function TrendSection({ projectId }: Props) {
  const { mode } = useTheme()
  const [days, setDays] = useState<30 | 90 | 365>(30)
  const [expanded, setExpanded] = useState(false) // 默认收起：版面简洁，点击展开才拉数据
  const [trend, setTrend] = useState<ProjectTrend | null>(null)
  const [loading, setLoading] = useState(false) // 懒加载：展开前不请求
  const [hidden, setHidden] = useState(false) // 403（专项）等 → 面板整体隐藏
  const divRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  // 懒加载：展开才请求（每次展开重新拉取拿最新数据；收起零请求）
  useEffect(() => {
    if (!expanded) return
    let stale = false
    setHidden(false) // 项目切换复位：专项 403 残留不连累下一个项目（对齐 health 先例的按次重取）
    setLoading(true)
    getProjectTrend(projectId, days)
      .then((data) => { if (!stale) setTrend(data) })
      .catch(() => { if (!stale) setHidden(true) }) // 专项 403 / 加载失败 → 隐藏区块（与 health 区块同模式）
      .finally(() => { if (!stale) setLoading(false) })
    return () => { stale = true }
  }, [projectId, days, expanded])

  const points = trend?.points ?? []
  const events = trend?.events ?? []
  const hasData = points.length > 0
  const daysNeeded = ACCUMULATING_TARGET_DAYS - points.length // 尚需天数（快照点数不足 7）

  useEffect(() => {
    if (!hasData || !divRef.current) return
    let cancelled = false
    let ro: ResizeObserver | null = null
    loadECharts().then((core) => {
      if (cancelled || !divRef.current) return
      chartRef.current?.dispose()
      const chart = core.init(divRef.current, mode === 'dark' ? 'dark' : undefined)

      // 双线：计划 vs 实际（缺口即偏差）；点位 [日期, 值]，null 断线（断开不补零）
      type PointMetrics = ProjectTrend['points'][number]['metrics']
      const lineData = (pick: (m: PointMetrics) => number | null) =>
        points.map((pt) => [pt.date, pick(pt.metrics)] as [string, number | null])

      // 三类事件点 → scatter 标记（同日多条 hover 明细合并；y 贴 0 只作标记不参与连线）
      const eventSeries = (['delayed', 'conflict', 'plan_change'] as const).map((kind) => {
        const byDate = new Map<string, string[]>()
        for (const e of events.filter((ev) => ev.kind === kind)) {
          const arr = byDate.get(e.date) ?? []
          arr.push(e.detail)
          byDate.set(e.date, arr)
        }
        const label = kind === 'delayed' ? '延期' : kind === 'conflict' ? '资源冲突' : '计划变更'
        return {
          name: label,
          type: 'scatter' as const,
          data: [...byDate.entries()].map(([date, details]) => ({
            value: [date, 0],
            tip: `${label}：${details.join('；')}`,
          })),
          symbolSize: 10,
          symbolOffset: [0, -5], // 符号整体浮于轴线上方（y=0 贴网格底；y 正值向下会坠进刻度标签带——评审 #9 源码实证）
          itemStyle: { color: EVENT_COLOR[kind] },
          tooltip: {
            // formatter 参数按 ECharts CallbackDataParams 签名，data 经 as 收窄取自定义 tip 字段
            formatter: (p: unknown) => {
              const d = (p as { data?: { tip?: string } }).data
              return d?.tip ?? ''
            },
          },
        }
      })

      const option: EChartsOption = {
        backgroundColor: 'transparent',
        animation: false,
        tooltip: {
          // 全局 formatter（axis 联动）：系列级 formatter 在 trigger:'axis' 下不被调用
          // （echarts 源码：axis 路径 model 级联不含系列模型；item 路径 trigger≠'item' 恒返回）——
          // 事件点明细 tip 必须在此按 seriesName 拼出（评审 #8 🔴）
          trigger: 'axis',
          formatter: (params: unknown) => {
            const list = (Array.isArray(params) ? params : [params]) as {
              seriesName?: string
              value?: [string, number | null] | unknown
              data?: { tip?: string }
            }[]
            const rows: string[] = []
            for (const p of list) {
              if (p.data?.tip) { rows.push(p.data.tip); continue } // 事件点：自定义明细
              const v = Array.isArray(p.value) ? p.value[1] : undefined
              if (p.seriesName && typeof v === 'number') {
                rows.push(`${p.seriesName}：${v}%`)
              }
            }
            return rows.length > 0 ? rows.join('<br/>') : ''
          },
        },
        legend: { top: 0, textStyle: { color: AXIS_TEXT[mode] } },
        grid: { left: 48, right: 24, top: 36, bottom: 28 },
        xAxis: {
          type: 'time',
          axisLabel: { color: AXIS_TEXT[mode] },
          splitLine: { show: false },
        },
        yAxis: {
          type: 'value',
          max: 100,
          axisLabel: { color: AXIS_TEXT[mode], formatter: '{value}%' },
          splitLine: { lineStyle: { color: SPLIT_LINE[mode] } },
        },
        series: [
          {
            name: '计划累计完成度',
            type: 'line',
            data: lineData((m) => m.plan_cum_pct),
            connectNulls: false, // 缺失日期断开（§3.5 验收②）
            lineStyle: { type: 'dashed' },
            emphasis: { focus: 'series' },
          },
          {
            name: '实际累计完成度',
            type: 'line',
            data: lineData((m) => m.actual_cum_pct),
            connectNulls: false,
            emphasis: { focus: 'series' },
          },
          ...eventSeries,
        ],
      }
      chart.setOption(option)
      chartRef.current = chart
      ro = new ResizeObserver(() => chartRef.current?.resize())
      ro.observe(divRef.current)
    })
    return () => {
      cancelled = true
      ro?.disconnect()
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [mode, points, events, hasData])

  if (hidden) return null

  return (
    <Card size="small" styles={{ body: { padding: 0 } }}>
      <Collapse
        activeKey={expanded ? ['trend'] : []}
        onChange={(keys) => setExpanded(keys.includes('trend'))}
        items={[{
          key: 'trend',
          label: (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              进度趋势
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                计划 vs 实际 · 事件点 · 点击展开
              </span>
            </span>
          ),
          // 展开后 header 右侧常驻时间窗切换（stopPropagation 避免点切换误收面板）
          extra: expanded ? (
            <span onClick={(e) => e.stopPropagation()}>
              <Segmented
                size="small"
                value={days}
                onChange={(v) => setDays(v as 30 | 90 | 365)}
                options={[
                  { label: '30 天', value: 30 },
                  { label: '90 天', value: 90 },
                  { label: '365 天', value: 365 },
                ]}
              />
            </span>
          ) : undefined,
          children: (
            <div style={{ padding: '4px 4px 8px' }}>
              {loading ? (
                <Spin style={{ display: 'block', margin: '48px auto' }} />
              ) : !hasData ? (
                <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: '36px 0' }}>
                  数据积累中 — 快照每日自动采集（只拍未开始/进行中项目），从上线日起算
                </div>
              ) : (
                <>
                  {points.length < ACCUMULATING_TARGET_DAYS && (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                      数据积累中（尚需 {daysNeeded} 天）
                    </div>
                  )}
                  {trend?.frozen && (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                      项目已搁置 · 趋势冻结于 {trend.frozen_date ?? '—'}
                    </div>
                  )}
                  <div ref={divRef} style={{ height: 260 }} />
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                    缺口即偏差（计划 vs 实际）· 停机/未采集日曲线断开不补零
                    {events.length > 0 && (
                      <>
                        {' '}· 事件点：
                        <span style={{ color: EVENT_COLOR.delayed }}>● 延期</span>
                        <span style={{ color: EVENT_COLOR.conflict, marginLeft: 8 }}>● 冲突</span>
                        <span style={{ color: EVENT_COLOR.plan_change, marginLeft: 8 }}>● 计划变更</span>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          ),
        }]}
      />
    </Card>
  )
}
