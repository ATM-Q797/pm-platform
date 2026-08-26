import { useEffect, useRef } from 'react'
import { applyGanttConfig, setScale, setCriticalHighlight } from './ganttConfig'
import { setupPan, cleanupPan } from './panUtils'
import { drawTodayMarker } from './todayMarker'
import { getProjectGantt, getProject, getCriticalPath } from '../../api/projects'
import { createDependency, deleteDependency } from '../../api/phases'
import { listResources } from '../../api/resources'
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css'
import './gantt.css'

interface Props {
  projectId: number
  scale?: 'day' | 'week' | 'month'
  showCritical?: boolean // 关键路径高亮开关（默认关）
  onPhaseClick: (phaseId: number) => void
}

export default function GanttChart({ projectId, scale = 'week', showCritical = false, onPhaseClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  // 保存 gantt 实例引用，供 scale 切换 useEffect 使用
  const ganttRef = useRef<any>(null)
  // 用 ref 同步最新的 scale 值，供初始化 useEffect（依赖 projectId）在
  // gantt.init 之后立即应用正确尺度，避免组件重建后尺度与 Segmented 控件不一致
  const scaleRef = useRef(scale)
  scaleRef.current = scale
  // 同步关键路径开关状态（初始化/切换时读取）
  const showCriticalRef = useRef(showCritical)
  showCriticalRef.current = showCritical
  // 缓存关键路径 phase id（避免重复请求）
  const criticalIdsRef = useRef<Set<number> | null>(null)

  // 切换关键路径开关：开 → 请求并高亮；关 → 清除高亮
  useEffect(() => {
    const gantt = ganttRef.current
    if (!gantt || !containerRef.current) return
    if (showCritical) {
      getCriticalPath(projectId).then((r) => {
        if (!showCriticalRef.current) return // 已切换关闭，丢弃结果
        criticalIdsRef.current = new Set(r.critical_phase_ids)
        setCriticalHighlight(criticalIdsRef.current)
        gantt.render()
      }).catch(() => {
        gantt.message({ text: '关键路径计算失败', type: 'error', expire: 3000 })
      })
    } else {
      criticalIdsRef.current = null
      setCriticalHighlight(null)
      gantt.render()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showCritical])

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
        // 初始开关打开：请求关键路径并准备高亮（render 时生效）
        if (showCriticalRef.current) {
          try {
            const cp = await getCriticalPath(projectId)
            criticalIdsRef.current = new Set(cp.critical_phase_ids)
            setCriticalHighlight(criticalIdsRef.current)
          } catch { /* 计算失败不阻塞甘特图渲染 */ }
        }
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

  return <div ref={containerRef} className="pm-gantt-container" style={{ width: '100%', height: 'clamp(420px, calc(100vh - 380px), 900px)' }} />
}

// dhtmlxGantt link type 映射："0"→FS "1"→SS "2"→FF "3"→SF
function mapLinkType(type: string): string {
  const map: Record<string, string> = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' }
  return map[type] || 'FS'
}

/**
 * 甘特图渲染完成后的回调（今日标记由共享 drawTodayMarker 绘制，见 todayMarker.ts）
 */
