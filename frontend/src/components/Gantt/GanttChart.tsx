import { useEffect, useRef } from 'react'
import { applyGanttConfig, setScale } from './ganttConfig'
import { getProjectGantt, getProject } from '../../api/projects'
import { updatePhase } from '../../api/phases'
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
        // scale 切换由独立的 useEffect 处理（通过 scale prop + ganttRef）
        // 点击编辑由容器的事件委托处理（只响应右侧任务条，不响应 grid 行），
        // 不使用 dhtmlxGantt 的 onTaskClick（它对 grid 行点击也触发）
        const dragH = gantt.attachEvent('onAfterTaskDrag', async (id: any, _mode: any) => {
          const tid = Number(id)
          const task = gantt.getTask(id)
          if (tid <= 0) return  // 跳过项目行
          const startDate = gantt.date.date_to_str('%Y-%m-%d')(task.start_date)
          const endDate = gantt.date.date_to_str('%Y-%m-%d')(gantt.calculateEndDate(task))
          const progress = Math.round((task.progress || 0) * 100)
          try {
            await updatePhase(tid, { plan_start: startDate, plan_end: endDate, progress })
            gantt.message({ text: `已保存：${task.text}`, expire: 1500 })
          } catch (e) {
            gantt.message({ text: '保存失败', type: 'error', expire: 3000 })
          }
        })
        handlers.push(dragH)
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

/**
 * 空白处拖动平移：在时间轴空白区按住左键拖动，实现左右平移。
 * 点甘特条/连线等可交互元素时不触发（交给 dhtmlx 的拖拽改期）。
 * 必须在 gantt.init() 之后调用（此时 .gantt_data_area DOM 已存在）。
 */
let _panCleanup: (() => void) | null = null

function cleanupPan() {
  if (_panCleanup) { _panCleanup(); _panCleanup = null }
}

function setupPan(gantt: any, container: HTMLElement) {
  // 先清理上次的监听（scale 切换重建时会重复调用）
  cleanupPan()

  const dataArea = container.querySelector('.gantt_data_area') as HTMLElement | null
  if (!dataArea) return

  let panning = false
  let panStartX = 0
  let panStartScroll = 0
  let panMoved = false

  const onMouseDown = (e: MouseEvent) => {
    const target = e.target as HTMLElement
    // 点到甘特条、连线、resize 手柄、今天标记等可交互元素时不启动平移
    if (target.closest('.gantt_task_line, .gantt_task_link, .gantt_link_arrow_right, .gantt_link_arrow_left, .gantt_task_progress_drag, .pm-today-marker')) {
      return
    }
    panning = true
    panMoved = false
    panStartX = e.clientX
    const st = gantt.getScrollState()
    panStartScroll = st ? st.x : 0
    dataArea.style.cursor = 'grabbing'
    e.preventDefault()
  }

  const onMouseMove = (e: MouseEvent) => {
    if (!panning) return
    const dx = e.clientX - panStartX
    if (Math.abs(dx) > 3) panMoved = true
    // scrollTo(x, y)：保持当前 y 不变，只改 x
    const st = gantt.getScrollState()
    gantt.scrollTo(panStartScroll - dx, st ? st.y : 0)
  }

  const onMouseUp = (e: MouseEvent) => {
    if (!panning) return
    panning = false
    dataArea.style.cursor = 'grab'
    // 拖动平移后阻止紧随的 click（避免误开编辑面板）
    if (panMoved) e.stopPropagation()
  }

  dataArea.addEventListener('mousedown', onMouseDown, true)  // capture 阶段，先于 dhtmlx 捕获
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  dataArea.style.cursor = 'grab'

  _panCleanup = () => {
    dataArea.removeEventListener('mousedown', onMouseDown, true)
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    dataArea.style.cursor = ''
  }
}

/**
 * 自绘"今天"标记线。
 *
 * dhtmlx-gantt 10.0 社区版没有内置 marker 插件（无 addMarker / markToday），
 * 这里用 posFromDate 算出今天在时间轴上的 X 坐标，自绘标记：
 *   - 顶部 ▼ 三角形（贴时间轴刻度下沿）+ "今天"文字标签
 *   - 中间红色虚线（只在任务条数据区垂直贯穿）
 *   - 底部 ▲ 三角形（贴任务区底部）
 * 标记挂在 .gantt_data_area（时间轴滚动容器）内，随时间轴横向滚动一起移动。
 */
function drawTodayMarker(gantt: any, container: HTMLElement) {
  // 清除旧标记（scale 切换 / 数据刷新时会重复调用）
  container.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())

  const dataArea = container.querySelector('.gantt_data_area') as HTMLElement | null
  if (!dataArea) return

  const x = gantt.posFromDate(new Date())
  if (typeof x !== 'number' || isNaN(x)) return

  const marker = document.createElement('div')
  marker.className = 'pm-today-marker'
  // marker 容器：覆盖整个 dataArea（任务条区域），垂直 flex 布局
  marker.style.cssText = `position:absolute;left:${x}px;top:0;height:100%;width:0;z-index:10;pointer-events:none;display:flex;flex-direction:column;align-items:center;justify-content:space-between;`

  // 顶部 ▼ 三角形 + "今天"标签（贴时间轴刻度下沿 / dataArea 顶部）
  const topCap = document.createElement('div')
  topCap.style.cssText = 'display:flex;flex-direction:column;align-items:center;line-height:1;'
  const label = document.createElement('div')
  label.textContent = '今天'
  label.style.cssText = 'font-size:11px;font-weight:600;color:#fff;background:#ff4d4f;padding:1px 6px;border-radius:3px;white-space:nowrap;margin-bottom:2px;'
  const triDown = document.createElement('div')
  triDown.style.cssText = 'width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid #ff4d4f;'
  topCap.appendChild(label)
  topCap.appendChild(triDown)

  // 中间红色虚线（absolute 定位，从顶部三角下方到底部三角上方）
  const dashedLine = document.createElement('div')
  dashedLine.style.cssText = 'position:absolute;left:50%;top:27px;bottom:6px;width:0;border-left:2px dashed #ff4d4f;transform:translateX(-50%);'

  // 底部 ▲ 三角形（贴 dataArea 底部，justify-content:space-between 让它自然贴底）
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
