import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Drawer, Segmented, Spin, Tag, Tooltip } from 'antd'
import { getHeatmap } from '../../api/resources'
import { getMe } from '../../api/auth'
import type { HeatmapCellPhase, HeatmapPerson, ResourceHeatmap, UserInfo } from '../../types'
import ConflictOverrideModal, { type OverrideTarget } from './ConflictOverrideModal'
import '../../styles/resourceHeatmap.css'

type Granularity = 'week' | 'month'
type WindowKey = '4' | '12' | '24' | '0'

/** 窗口选项：0=全部（最早数据日期 → 今天） */
const WINDOW_OPTIONS: { label: string; value: WindowKey; weeks: number }[] = [
  { label: '4周', value: '4', weeks: 4 },
  { label: '12周', value: '12', weeks: 12 },
  { label: '24周', value: '24', weeks: 24 },
  { label: '全部', value: '0', weeks: 0 },
]

/** 窗口 ≥24 周自动切月（用户决策 3：Segmented 联动，周选项禁用+提示） */
const AUTO_MONTH_THRESHOLD = 24

/** 格子颜色分级（设计 §一：活跃数 → 深浅双主题） */
function cellLevelClass(count: number, conflict: boolean): string {
  const level = count >= 3 ? 'lv3' : count === 2 ? 'lv2' : count === 1 ? 'lv1' : 'empty'
  return `hm-cell ${level}${conflict ? ' has-conflict' : ''}`
}

function fmtDate(s: string): string {
  return s.slice(5).replace('-', '/') // MM/DD（紧凑列头/tooltip 用）
}

/** 列头标签：周=M/D，月=YYYY-MM */
function colLabel(col: string, granularity: Granularity): string {
  return granularity === 'month' ? col.slice(0, 7) : fmtDate(col)
}

/** Drawer 周期标题后缀（评审处置 #9） */
function periodTitle(col: string, granularity: Granularity): string {
  return granularity === 'month' ? `${col.slice(0, 7)} 当月` : `${col} 当周`
}

/** 该列是否含今天（今日线位置） */
function columnHasToday(col: string, granularity: Granularity, todayStr: string): boolean {
  if (granularity === 'month') return todayStr.slice(0, 7) === col.slice(0, 7)
  // 周桶：col 为周一，今天在 [col, col+6] 内
  const colDate = new Date(col + 'T00:00:00')
  const today = new Date(todayStr + 'T00:00:00')
  const diff = Math.floor((today.getTime() - colDate.getTime()) / 86400000)
  return diff >= 0 && diff <= 6
}

interface CellDrawerState {
  person: HeatmapPerson
  colIndex: number
}

export default function HeatmapView() {
  const navigate = useNavigate()
  const [windowKey, setWindowKey] = useState<WindowKey>('12')
  const [granularity, setGranularity] = useState<Granularity>('week')
  const [data, setData] = useState<ResourceHeatmap | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<CellDrawerState | null>(null)
  const [idleExpanded, setIdleExpanded] = useState(false)
  const [hoverRow, setHoverRow] = useState<number | null>(null)
  const [me, setMe] = useState<UserInfo | null>(null)
  const [overrideTarget, setOverrideTarget] = useState<OverrideTarget | null>(null)
  const [reloadFlag, setReloadFlag] = useState(0)

  // 当前用户（消除按钮仅 admin/manager 显示，评审处置 #6）
  useEffect(() => {
    getMe().then(setMe).catch(() => {})
  }, [])
  const canOverride = me?.role === 'admin' || me?.role === 'manager'

  const weeks = WINDOW_OPTIONS.find((w) => w.value === windowKey)!.weeks
  /** ≥24 周（或全部）时周粒度禁用并强制月（用户决策 3） */
  const weekDisabled = weeks === 0 || weeks >= AUTO_MONTH_THRESHOLD
  const effectiveGranularity: Granularity = weekDisabled ? 'month' : granularity

  const todayStr = useMemo(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getHeatmap({ weeks, granularity: effectiveGranularity })
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || '热力数据加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [weeks, effectiveGranularity, reloadFlag])

  /** ≥24 周（或全部）时周粒度禁用并强制月；切回短窗口保留当前粒度（用户可手动切换） */

  // 切窗口/粒度后关闭 Drawer（数据列已变，旧 index 失效）
  useEffect(() => {
    setDrawer(null)
  }, [windowKey, effectiveGranularity])

  const drawerPhases: HeatmapCellPhase[] = drawer && data
    ? data.people.find((p) => p.resource_id === drawer.person.resource_id)?.cell_phases[drawer.colIndex] ?? []
    : []

  const drawerCol = drawer && data ? data.columns[drawer.colIndex] : ''

  const handleWindowChange = (val: WindowKey) => {
    setWindowKey(val)
    if (val === '0' || Number(val) >= AUTO_MONTH_THRESHOLD) {
      // ≥24 周/全部 → 自动切月（决策 3）
      setGranularity('month')
    }
  }

  return (
    <div className="hm-wrap">
      <div className="hm-toolbar">
        <span className="hm-toolbar-label">时间窗口</span>
        <Segmented
          options={WINDOW_OPTIONS.map((w) => ({ label: w.label, value: w.value }))}
          value={windowKey}
          onChange={(v) => handleWindowChange(v as WindowKey)}
        />
        <span className="hm-toolbar-label">粒度</span>
        <Segmented
          options={[
            { label: '周', value: 'week', disabled: weekDisabled },
            { label: '月', value: 'month' },
          ]}
          value={effectiveGranularity}
          onChange={(v) => setGranularity(v as Granularity)}
        />
        {weekDisabled && (
          <span className="hm-hint">窗口 ≥24 周自动按月聚合（周粒度已禁用）</span>
        )}
        {data && (
          <span className="hm-hint">
            {data.start_date} ~ {data.end_date} · {data.people.length} 人有负载 · {data.idle_people.length} 人空闲
          </span>
        )}
      </div>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 8 }} />}
      {loading && <Spin style={{ display: 'block', margin: '24px auto' }} />}

      {!loading && data && (
        <>
          <div className="hm-scroll">
            <div
              className="hm-grid"
              style={{ gridTemplateColumns: `200px repeat(${data.columns.length}, minmax(34px, 1fr)) 96px` }}
            >
              {/* 表头行 */}
              <div className="hm-corner">人员（负载↓）</div>
              {data.columns.map((col) => (
                <div key={col} className={`hm-col-head${columnHasToday(col, data.granularity, todayStr) ? ' today' : ''}`}>
                  {colLabel(col, data.granularity)}
                  {columnHasToday(col, data.granularity, todayStr) && <span className="hm-today-tag">今天</span>}
                </div>
              ))}
              <div className="hm-col-head hm-load-head">负载</div>

              {/* 人员行（hoverRow 高亮整行，便于对列） */}
              {data.people.map((person) => (
                <PersonRow
                  key={person.resource_id}
                  person={person}
                  data={data}
                  hovered={hoverRow === person.resource_id}
                  onHover={(hovering) => setHoverRow(hovering ? person.resource_id : null)}
                  onCellClick={(colIndex) => setDrawer({ person, colIndex })}
                />
              ))}
            </div>
          </div>

          {/* 空闲区（可折叠，设计 §3.2） */}
          {data.idle_people.length > 0 && (
            <div className="hm-idle">
              <button type="button" className="hm-idle-toggle" onClick={() => setIdleExpanded((v) => !v)}>
                {idleExpanded ? '▾' : '▸'} 空闲人员（{data.idle_people.length}）— 窗口内零负载
              </button>
              {idleExpanded && (
                <div className="hm-idle-list">
                  {data.idle_people.map((p) => (
                    <Tag key={p.resource_id}>
                      {p.name}
                      {p.role ? ` · ${p.role}` : ''}
                    </Tag>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* 点击格子 → Drawer（用户决策 4） */}
      <Drawer
        open={drawer !== null}
        onClose={() => setDrawer(null)}
        width={420}
        title={
          drawer && data
            ? `${drawer.person.name} · ${periodTitle(drawerCol, data.granularity)}活跃阶段`
            : ''
        }
      >
        {drawerPhases.length === 0 ? (
          <div className="hm-drawer-empty">该时段无活跃阶段</div>
        ) : (
          <div className="hm-drawer-list">
            {drawerPhases.map((e) => (
              <div
                key={e.phase_id}
                className={`hm-drawer-item${e.conflict ? ' conflict' : ''}`}
                onClick={() => {
                  setDrawer(null)
                  navigate(`/projects/${e.project_id}`)
                }}
              >
                <div className="hm-drawer-title">
                  <span className="hm-drawer-project">{e.project_name}</span>
                  <span className="hm-drawer-phase">{e.phase_name}</span>
                  {e.conflict && <span className="hm-conflict-mark">⚠ 冲突</span>}
                </div>
                <div className="hm-drawer-meta">
                  <span>{e.start} ~ {e.end}</span>
                  {e.status && <Tag className="hm-drawer-status">{e.status}</Tag>}
                </div>
                {e.conflict && e.conflict_detail && (
                  <div className="hm-drawer-conflict-line">
                    <span className="hm-conflict-detail">
                      ⚠ 与 {e.conflict_detail.partner_name}·{e.conflict_detail.partner_phase_name}{' '}
                      重叠 {e.conflict_detail.overlap_days} 天
                    </span>
                    {canOverride && (
                      <Button
                        size="small"
                        danger
                        onClick={(ev) => {
                          ev.stopPropagation() // 不触发整行跳转
                          setOverrideTarget({
                            resourceId: drawer!.person.resource_id,
                            resourceName: drawer!.person.name,
                            phaseAId: e.conflict_detail!.phase_a_id,
                            phaseBId: e.conflict_detail!.phase_b_id,
                            summary: `${drawer!.person.name}：${e.project_name}·${e.phase_name} × ` +
                              `${e.conflict_detail!.partner_name}·${e.conflict_detail!.partner_phase_name}` +
                              `（重叠 ${e.conflict_detail!.overlap_days} 天）`,
                          })
                        }}
                      >
                        消除
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Drawer>

      {/* 消除冲突弹窗（评审处置 #6：仅 admin/manager 入口可见） */}
      <ConflictOverrideModal
        target={overrideTarget}
        open={overrideTarget !== null}
        onClose={() => setOverrideTarget(null)}
        onOverridden={() => {
          setReloadFlag((f) => f + 1) // 重新拉热力：⚠ 消失、格值不变
        }}
      />
    </div>
  )
}

function PersonRow({
  person,
  data,
  hovered,
  onHover,
  onCellClick,
}: {
  person: HeatmapPerson
  data: ResourceHeatmap
  hovered: boolean
  onHover: (hovering: boolean) => void
  onCellClick: (colIndex: number) => void
}) {
  const rowCls = hovered ? ' row-hover' : ''
  return (
    <>
      <div
        className={`hm-row-head${rowCls}`}
        title={person.role ? `${person.name}（${person.role}）` : person.name}
        onMouseEnter={() => onHover(true)}
        onMouseLeave={() => onHover(false)}
      >
        <span className="hm-name">{person.name}</span>
        {person.role && <span className="hm-role">{person.role}</span>}
      </div>
      {data.columns.map((col, i) => {
        const count = person.cells[i] ?? 0
        const entries = person.cell_phases[i]
        const hasConflict = !!entries?.some((e) => e.conflict)
        const cell = (
          <div
            key={col}
            className={`${cellLevelClass(count, hasConflict)}${rowCls}`}
            onClick={() => entries && onCellClick(i)}
            role={entries ? 'button' : undefined}
          >
            {hasConflict && <span className="hm-conflict-badge">⚠</span>}
          </div>
        )
        if (!entries || entries.length === 0) return <div key={col} className={`hm-cell empty${rowCls}`} />
        return (
          <Tooltip
            key={col}
            title={<CellTooltip person={person} entries={entries} col={col} granularity={data.granularity} />}
            placement="top"
          >
            {cell}
          </Tooltip>
        )
      })}
      <div
        className={`hm-load-cell${rowCls}`}
        title="窗口内峰值并行数 / 活跃阶段总数"
        onMouseEnter={() => onHover(true)}
        onMouseLeave={() => onHover(false)}
      >
        <span className={`hm-peak${person.peak_parallel >= 3 ? ' high' : ''}`}>{person.peak_parallel}并行</span>
        <span className="hm-active-total">{person.active_phases}阶段</span>
      </div>
    </>
  )
}

function CellTooltip({
  person,
  entries,
  col,
  granularity,
}: {
  person: HeatmapPerson
  entries: HeatmapCellPhase[]
  col: string
  granularity: Granularity
}) {
  const MAX = 6 // 最多显示 6 条 + "等 N 个"（设计 §3.3）
  const shown = entries.slice(0, MAX)
  const rest = entries.length - shown.length
  return (
    <div className="hm-tooltip">
      <div className="hm-tooltip-head">
        {person.name} · {periodTitle(col, granularity)} · {entries.length} 个阶段
      </div>
      {shown.map((e) => (
        <div key={e.phase_id} className={`hm-tooltip-item${e.conflict ? ' conflict' : ''}`}>
          <span className="hm-tooltip-dot">·</span>
          <span>
            {e.project_name} · {e.phase_name}（{e.start.slice(5)}~{e.end.slice(5)}）
            {e.conflict && <span className="hm-conflict-mark"> ⚠</span>}
            {e.conflict && e.conflict_detail && (
              <span className="hm-tooltip-conflict">
                {' '}与 {e.conflict_detail.partner_name}·{e.conflict_detail.partner_phase_name}
                {' '}重叠 {e.conflict_detail.overlap_days} 天
              </span>
            )}
          </span>
        </div>
      ))}
      {rest > 0 && <div className="hm-tooltip-more">等 {rest} 个…</div>}
    </div>
  )
}
