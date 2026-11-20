import { useEffect, useRef, useState } from 'react'
import { Segmented, Spin, Button, Empty } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { applyGanttConfig, setScale, setCriticalHighlight } from '../Gantt/ganttConfig'
import { setupPan, cleanupPan } from '../Gantt/panUtils'
import { drawTodayMarker } from '../Gantt/todayMarker'
import { getOverviewGantt } from '../../api/overviewGantt'
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css'
import '../Gantt/gantt.css'
import './overviewGantt.css'

interface Props {
  /** 点击阶段条回调（父级跳详情页；项目行不触发） */
  onPhaseClick: (projectId: number, phaseId: number) => void
}

/**
 * 进行中项目总览甘特（项目总览甘特批 2026-11-19）。
 *
 * 与 GanttChart（详情页单项目甘特）的差异：
 * - 数据源一次聚合请求 /projects/overview-gantt（多项目拼接，项目行负 id）
 * - 只读视图：禁拖拽/连线/编辑，点击阶段条 → 跳对应详情页
 * - 阶段状态直接由后端下发（status 字段）着色，无需前端再拉详情补齐
 * 生命周期模式与 ResourceView 同型（动态 import dhtmlx、卸载 clearAll + cleanupPan）。
 */
export default function OverviewGantt({ onPhaseClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const ganttRef = useRef<any>(null)
  const onPhaseClickRef = useRef(onPhaseClick)
  onPhaseClickRef.current = onPhaseClick
  const scaleRef = useRef<'day' | 'week' | 'month'>('week')
  const [scale, setScaleState] = useState<'day' | 'week' | 'month'>('week')
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [taskCount, setTaskCount] = useState(0)
  // 刷新走重建（reloadFlag 同型——ResourceView 先例）：自增触发 effect 重跑，
  // 闭包内 gantt 实例整体重建，数据一致性优先（进行中项目行数小，重建成本可忽略）
  const [reloadFlag, setReloadFlag] = useState(0)

  useEffect(() => {
    let gantt: any = null
    let destroyed = false

    const init = async () => {
      setLoading(true)
      setFailed(null)
      try {
        const mod = await import('dhtmlx-gantt')
        gantt = mod.gantt
        ganttRef.current = gantt
        if (destroyed || !containerRef.current) return

        applyGanttConfig(gantt)
        // 防御性复位关键路径高亮全局态：GanttChart 卸载不复位 criticalHighlightIds（模块级全局），
        // 携高亮态离开详情页再进总览，同项目阶段条残留红框（代码评审轮次 2 #3）
        setCriticalHighlight(null)

        // 总览视图：左侧栏保留 项目/阶段、负责人/参与人（合并列：项目行显负责人、阶段行显参与人，
        // owner_name 与 assignee_names 后端直接下发）
        gantt.config.columns = [
          { name: 'text', label: '项目 / 阶段', width: 300, tree: true },
          { name: 'assignees', label: '负责人/参与人', width: 110, align: 'center',
            template: (task: any) => task.owner_name || task.assignee_names || '' },
          { name: 'start_date', label: '开始', width: 90, align: 'center' },
          { name: 'duration', label: '工期', width: 60, align: 'center' },
        ]

        // 只读：总览不做任何编辑交互（编辑入口在详情页甘特）
        gantt.config.drag_move = false
        gantt.config.drag_resize = false
        gantt.config.drag_progress = false
        gantt.config.drag_links = false
        gantt.config.touch = false
        gantt.config.order_branch = false
        // 注意不开 config.readonly：readonly 会连行内展开/收起一起禁掉，总览需要树形展开

        const ganttData = await getOverviewGantt()
        if (destroyed) return
        setTaskCount(ganttData.data.length)

        gantt.init(containerRef.current)
        gantt.clearAll()
        gantt.parse({ data: ganttData.data, links: ganttData.links })
        gantt.render()
        setScale(gantt, scaleRef.current)
        drawTodayMarker(gantt, containerRef.current)
        // 初始视口定位到今天（用户核心诉求：直观看到当前时间线）——
        // 仅加载时定位；尺度切换不调用，避免重置用户滚动位置
        gantt.showDate(new Date())
        // 空白处拖拽平移：与项目甘特/资源负载一致（必须在 gantt.init() 之后）
        setupPan(gantt, containerRef.current)
      } catch (e) {
        console.error('OverviewGantt 初始化失败:', e)
        if (!destroyed) setFailed((e as Error).message || '加载失败')
      } finally {
        if (!destroyed) setLoading(false)
      }
    }
    init()

    // 点击捕获：只对右侧任务条（.gantt_task_line）响应——项目行（负 id）不跳转，
    // 阶段条（正 id）携带归属项目 id 跳详情页（左侧 grid 行点击 = 展开/收起，维持 dhtmlx 默认）
    const handleContainerClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const taskBar = target.closest('.gantt_task_line') as HTMLElement | null
      if (taskBar) {
        const tid = Number(taskBar.getAttribute('task_id'))
        const task = ganttRef.current?.getTask?.(tid)
        if (task && task.type === 'task' && task.project_id) {
          onPhaseClickRef.current(task.project_id, tid)
        }
      }
    }
    const container = containerRef.current
    container?.addEventListener('click', handleContainerClick)

    return () => {
      destroyed = true
      container?.removeEventListener('click', handleContainerClick)
      cleanupPan()
      if (gantt) { gantt.clearAll() }
    }
  }, [reloadFlag])

  // 尺度切换：与 GanttChart 同型——setScale 内部已 render，渲染后重绘今日线
  useEffect(() => {
    if (ganttRef.current && containerRef.current) {
      setScale(ganttRef.current, scale)
      setTimeout(() => drawTodayMarker(ganttRef.current, containerRef.current!), 0)
    }
  }, [scale])

  if (failed) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Empty description={`总览甘特加载失败：${failed}`} />
        <Button icon={<ReloadOutlined />} onClick={() => setReloadFlag((n) => n + 1)} style={{ marginTop: 12 }}>
          重试
        </Button>
      </div>
    )
  }

  return (
    <Spin spinning={loading}>
      <div className="pm-toolbar" style={{ marginBottom: 8, display: 'flex', justifyContent: 'flex-end' }}>
        <Segmented
          value={scale}
          onChange={(v) => setScaleState(v as 'day' | 'week' | 'month')}
          options={[
            { label: '日', value: 'day' },
            { label: '周', value: 'week' },
            { label: '月', value: 'month' },
          ]}
        />
      </div>
      <div ref={containerRef} className="pm-gantt-container overview-gantt" style={{ width: '100%', height: 'calc(100vh - 300px)' }} />
      {taskCount === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-tertiary)' }}>
          当前没有进行中的项目
        </div>
      )}
    </Spin>
  )
}
