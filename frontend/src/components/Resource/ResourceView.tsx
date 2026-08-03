import { useEffect, useRef } from 'react'
import { applyGanttConfig, setScale } from '../Gantt/ganttConfig'
import { setupPan, cleanupPan } from '../Gantt/panUtils'
import { getAllWorkloads } from '../../api/resources'
import type { ResourceWorkload } from '../../types'
import '../Gantt/gantt.css'
import './resourceView.css'

interface Props {
  scale?: 'day' | 'week' | 'month'
  onPhaseClick: (phaseId: number) => void
}

// 阶段状态 → CSS class（与 GanttChart 一致，用于甘特条着色）
const STATUS_CLASS: Record<string, string> = {
  已完成: 'gantt-task-done',
  进行中: 'gantt-task-active',
  未开始: 'gantt-task-pending',
  延期: 'gantt-task-delayed',
  已搁置: 'gantt-task-blocked',
}

/**
 * 资源负载视图：多行甘特图，每人一行。
 *
 * 数据组织：每个人作为一个"项目"行（type=project），其参与的阶段作为子任务（type=task）。
 * 这样 dhtmlxGantt 天然呈现"每人一行，行内显示其阶段"的布局。
 *
 * 人员行 id 用负数（-personId），阶段行 id 用 phase_id（正数），避免冲突。
 */
export default function ResourceView({ scale = 'week', onPhaseClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const ganttRef = useRef<any>(null)
  const scaleRef = useRef(scale)
  scaleRef.current = scale

  useEffect(() => {
    let gantt: any = null
    let destroyed = false
    const handlers: string[] = []

    const init = async () => {
      try {
        const mod = await import('dhtmlx-gantt')
        gantt = mod.gantt
        ganttRef.current = gantt
        if (destroyed || !containerRef.current) return

        ensureGanttCss()
        applyGanttConfig(gantt)

        // 负载视图：禁用所有编辑交互，仅查看
        gantt.config.drag_move = false
        gantt.config.drag_resize = false
        gantt.config.drag_progress = false
        gantt.config.drag_links = false
        // 禁用右键菜单（防止误删除连线等操作）
        gantt.config.touch = false
        gantt.config.order_branch = false

        // 加载全员负载数据
        const allWorkloads: ResourceWorkload[] = await getAllWorkloads()
        if (destroyed) return

        // 过滤掉没有阶段的人员（不显示空行）
        const withWork = allWorkloads.filter((w) => w.workloads.length > 0)

        // 组装 dhtmlxGantt 数据
        const tasks: any[] = []
        const today = new Date()

        for (const wl of withWork) {
          const personRowId = -wl.resource.id // 负数避免与 phase_id 冲突
          // 计算该人员所有阶段的最早开始 / 最晚结束，作为人员行的时间范围
          const dates = wl.workloads
            .flatMap((w) => [w.plan_start, w.plan_end])
            .filter((d): d is string => !!d)
            .map((d) => new Date(d))
          const minDate = dates.length ? new Date(Math.min(...dates.map((d) => d.getTime()))) : today
          const maxDate = dates.length ? new Date(Math.max(...dates.map((d) => d.getTime()))) : today

          // 人员行（type=project，显示姓名 + 阶段数）
          tasks.push({
            id: personRowId,
            text: `${wl.resource.name}${wl.resource.role ? '（' + wl.resource.role + '）' : ''}`,
            start_date: fmt(minDate),
            duration: Math.max(1, Math.ceil((maxDate.getTime() - minDate.getTime()) / 86400000)),
            progress: 0,
            parent: 0,
            type: 'project',
            open: true,
          })

          // 该人员的每个阶段作为子任务
          for (const w of wl.workloads) {
            const start = w.plan_start ? new Date(w.plan_start) : today
            const end = w.plan_end ? new Date(w.plan_end) : today
            // 注意：id 必须全局唯一。同一阶段可能被多人参与（phase_id 重复），
            // 直接用 phase_id 会导致 dhtmlxGantt 内部索引混乱、甘特条错位。
            // 用 personId * 100000 + phaseId 保证唯一，真实 phase_id 存在自定义字段。
            tasks.push({
              id: wl.resource.id * 100000 + w.phase_id,
              text: `${w.project_name} · ${w.phase_name}`,
              start_date: fmt(start),
              duration: Math.max(1, Math.ceil((end.getTime() - start.getTime()) / 86400000)),
              progress: w.status === '已完成' ? 1 : w.status === '进行中' ? 0.5 : 0,
              parent: personRowId,
              type: 'task',
              open: true,
              status: w.status, // 供 task_class 着色
              project_name: w.project_name,
              phase_id: w.phase_id, // 真实阶段 id，点击时取这个
            })
          }
        }

        gantt.init(containerRef.current)
        gantt.clearAll()
        gantt.parse({ data: tasks, links: [] })
        gantt.render()
        setScale(gantt, scaleRef.current)
        drawTodayMarker(gantt, containerRef.current)
        // 启用空白处拖拽平移（与项目甘特图一致）
        setupPan(gantt, containerRef.current)
      } catch (e) {
        console.error('ResourceView 初始化失败:', e)
      }
    }
    init()

    // 点击事件委托：只响应任务条（type=task），点击后打开阶段详情
    const handleContainerClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const taskBar = target.closest('.gantt_task_line') as HTMLElement | null
      if (taskBar) {
        const tid = taskBar.getAttribute('task_id')
        if (tid && Number(tid) > 0) {
          // tid 是唯一 id（personId*100000+phaseId），通过 gantt 实例取真实 phase_id
          const g = ganttRef.current
          if (g) {
            const task = g.getTask(tid)
            if (task && task.phase_id) {
              onPhaseClick(task.phase_id)
              return
            }
          }
          // 兜底：tid 大于 100000 时取模还原 phase_id
          onPhaseClick(Number(tid) % 100000)
        }
      }
    }
    containerRef.current?.addEventListener('click', handleContainerClick)

    return () => {
      destroyed = true
      containerRef.current?.removeEventListener('click', handleContainerClick)
      cleanupPan()
      if (gantt) {
        for (const h of handlers) gantt.detachEvent(h)
        gantt.clearAll()
      }
    }
  }, [])

  // 尺度切换
  useEffect(() => {
    if (ganttRef.current) {
      setScale(ganttRef.current, scale)
      if (containerRef.current) {
        setTimeout(() => drawTodayMarker(ganttRef.current, containerRef.current!), 0)
      }
    }
  }, [scale])

  return <div ref={containerRef} className="pm-gantt-container resource-view" style={{ width: '100%', height: '70vh' }} />
}

function fmt(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

let cssLoaded = false
function ensureGanttCss() {
  if (cssLoaded) return
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = '/node_modules/dhtmlx-gantt/codebase/dhtmlxgantt.css'
  document.head.appendChild(link)
  cssLoaded = true
}

// 今天标记线（与 GanttChart 相同的自绘逻辑）
function drawTodayMarker(gantt: any, container: HTMLElement) {
  container.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())
  const dataArea = container.querySelector('.gantt_data_area') as HTMLElement | null
  if (!dataArea) return
  const x = gantt.posFromDate(new Date())
  if (typeof x !== 'number' || isNaN(x)) return

  const marker = document.createElement('div')
  marker.className = 'pm-today-marker'
  marker.style.cssText = `position:absolute;left:${x}px;top:0;height:100%;width:0;z-index:10;pointer-events:none;display:flex;flex-direction:column;align-items:center;justify-content:space-between;`
  const topCap = document.createElement('div')
  topCap.style.cssText = 'display:flex;flex-direction:column;align-items:center;line-height:1;'
  const label = document.createElement('div')
  label.textContent = '今天'
  label.style.cssText = 'font-size:11px;font-weight:600;color:#fff;background:#ff4d4f;padding:1px 6px;border-radius:3px;white-space:nowrap;margin-bottom:2px;'
  const triDown = document.createElement('div')
  triDown.style.cssText = 'width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid #ff4d4f;'
  topCap.appendChild(label)
  topCap.appendChild(triDown)
  const dashedLine = document.createElement('div')
  dashedLine.style.cssText = 'position:absolute;left:50%;top:27px;bottom:6px;width:0;border-left:2px dashed #ff4d4f;transform:translateX(-50%);'
  const bottomCap = document.createElement('div')
  bottomCap.style.cssText = 'display:flex;flex-direction:column;align-items:center;line-height:1;'
  const triUp = document.createElement('div')
  triUp.style.cssText = 'width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:6px solid #ff4d4f;'
  bottomCap.appendChild(triUp)
  marker.appendChild(topCap)
  marker.appendChild(dashedLine)
  marker.appendChild(bottomCap)
  dataArea.appendChild(marker)
}
