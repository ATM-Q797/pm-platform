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
        gantt.markToday()
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
      if (gantt) { for (const h of handlers) gantt.detachEvent(h); gantt.clearAll() }
    }
  }, [projectId])

  // 尺度切换：scale 变化时调用 setScale 重新渲染时间轴
  useEffect(() => {
    if (ganttRef.current) {
      setScale(ganttRef.current, scale)
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
