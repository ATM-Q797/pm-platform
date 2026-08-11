import { useEffect, useRef } from 'react'
import { applyGanttConfig, setScale } from './ganttConfig'
import { setupPan, cleanupPan } from './panUtils'
import { getProjectGantt, getProject } from '../../api/projects'
import { createDependency, deleteDependency } from '../../api/phases'
import { listResources } from '../../api/resources'
import './gantt.css'

interface Props {
  projectId: number
  scale?: 'day' | 'week' | 'month'
  onPhaseClick: (phaseId: number) => void
}

export default function GanttChart({ projectId, scale = 'week', onPhaseClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  // 保存 gantt 实例引用，供 scale 切换 useEffect 使用
  const ganttRef = useRef<any>(null)
  // 用 ref 同步最新的 scale 值，供初始化 useEffect（依赖 projectId）在
  // gantt.init 之后立即应用正确尺度，避免组件重建后尺度与 Segmented 控件不一致
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
        // 拖拽创建依赖连线 → 保存到后端
        const linkAddH = gantt.attachEvent('onAfterLinkAdd', async (_id: any, link: any) => {
          try {
            await createDependency(projectId, {
              from_phase_id: link.source,
              to_phase_id: link.target,
              type: mapLinkType(link.type),
            })
            gantt.message({ text: '已创建依赖', expire: 1500 })
          } catch (e) {
            gantt.message({ text: '创建依赖失败', type: 'error', expire: 3000 })
          }
        })
        handlers.push(linkAddH)
        // 删除依赖连线（右键点击连线→删除）
        const linkDelH = gantt.attachEvent('onAfterLinkDelete', async (id: any) => {
          try {
            await deleteDependency(Number(id))
            gantt.message({ text: '已删除依赖', expire: 1500 })
          } catch (e) {
            gantt.message({ text: '删除依赖失败', type: 'error', expire: 3000 })
          }
        })
        handlers.push(linkDelH)
        const [ganttData, projectDetail, resources] = await Promise.all([
          getProjectGantt(projectId), getProject(projectId), listResources(),
        ])
        if (destroyed) return
        const phaseMap = new Map<number, any>()
        for (const ph of projectDetail.phases || []) phaseMap.set(ph.id, ph)
        const resourceMap = new Map<number, string>()
        for (const r of resources) resourceMap.set(r.id, r.name)
        const tasks = ganttData.data.map((t: any) => {
          const phase = phaseMap.get(t.id)
          const enriched: any = { ...t }
          if (phase) {
            enriched.status = phase.status
            enriched.assignee_names = phase.assignees?.map((a: any) => resourceMap.get(a.id) || a.name).join('、') || ''
          }
          return enriched
        })
        gantt.init(containerRef.current)
        gantt.clearAll()
        gantt.parse({ data: tasks, links: ganttData.links })
        gantt.render()
        // 初始化后立即应用当前 scale（组件重建时保持编辑前的尺度一致）
        setScale(gantt, scaleRef.current)
        // 今天标记线：dhtmlx-gantt 10.0 社区版无内置 marker 插件，
        // 用 posFromDate 算出今天在时间轴上的 X 坐标，自绘一条竖线。
        drawTodayMarker(gantt, containerRef.current)

        // 空白处拖动平移：在时间轴空白区按住左键拖动，实现左右平移。
        // 必须在 gantt.init() 之后注册（此时 .gantt_data_area DOM 已创建）。
        setupPan(gantt, containerRef.current)
      } catch (e) {
        console.error('GanttChart 初始化失败:', e)
      }
    }
    init()

    // 点击捕获：只对右侧甘特图任务条（.gantt_task_line）触发编辑，
    // 不响应左侧 grid 行（.gantt_row）的点击
    const handleContainerClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      // 只匹配任务条（gantt_task_line），不匹配 grid 行（gantt_row）
      const taskBar = target.closest('.gantt_task_line') as HTMLElement | null
      if (taskBar) {
        const tid = Number(taskBar.getAttribute('task_id'))
        if (tid > 0) onPhaseClick(tid)  // 跳过项目行（id 为负）
      }
    }
    containerRef.current?.addEventListener('click', handleContainerClick)

    return () => {
      destroyed = true
      containerRef.current?.removeEventListener('click', handleContainerClick)
      cleanupPan()
      if (gantt) { for (const h of handlers) gantt.detachEvent(h); gantt.clearAll() }
    }
  }, [projectId])

  // 尺度切换：scale 变化时调用 setScale 重新渲染时间轴，并重绘今天标记线
  useEffect(() => {
    if (ganttRef.current) {
      setScale(ganttRef.current, scale)
      // setScale 内部调了 render()，这里在渲染后重绘标记线（新坐标）
      if (containerRef.current) {
        setTimeout(() => drawTodayMarker(ganttRef.current, containerRef.current!), 0)
      }
    }
  }, [scale])

  return <div ref={containerRef} className="pm-gantt-container" style={{ width: '100%', height: '60vh' }} />
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

// dhtmlxGantt link type 映射："0"→FS "1"→SS "2"→FF "3"→SF
function mapLinkType(type: string): string {
  const map: Record<string, string> = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' }
  return map[type] || 'FS'
}

/**
 * 自绘"今天"标记 — 挂在于时间轴可视区顶部，冻结在日期刻度位置。
 * 挂在 .gantt_task 内（覆盖时间轴可视区的背景层），该元素随横向滚动但不纵向滚动。
 */
function drawTodayMarker(gantt: any, container: HTMLElement) {
  container.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())

  // .gantt_task 是时间轴背景区域，固定在可视区内不随任务行纵向滚动
  const taskArea = container.querySelector('.gantt_task') as HTMLElement | null
  if (!taskArea) return

  // 清除旧标记
  taskArea.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())

  const x = gantt.posFromDate(new Date())
  if (typeof x !== 'number' || isNaN(x)) return

  const marker = document.createElement('div')
  marker.className = 'pm-today-marker'
  marker.style.cssText = `position:absolute;left:${x}px;top:2px;z-index:10;pointer-events:none;white-space:nowrap;`

  const label = document.createElement('span')
  label.textContent = '今天'
  label.style.cssText = 'font-size:10px;font-weight:600;color:#fff;background:#ff4d4f;padding:1px 4px;border-radius:2px;margin-right:2px;'

  const arrow = document.createElement('span')
  arrow.innerHTML = '▼'
  arrow.style.cssText = 'color:#ff4d4f;font-size:8px;'

  marker.appendChild(label)
  marker.appendChild(arrow)
  taskArea.appendChild(marker)
}
