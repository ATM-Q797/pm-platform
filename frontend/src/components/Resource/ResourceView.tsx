import { useEffect, useRef, useState } from 'react'
import { applyGanttConfig, setScale } from '../Gantt/ganttConfig'
import { setupPan, cleanupPan } from '../Gantt/panUtils'
import { drawTodayMarker } from '../Gantt/todayMarker'
import { getAllWorkloads, getResourceConflicts } from '../../api/resources'
import { getMe } from '../../api/auth'
import ConflictOverrideModal, { type OverrideTarget } from './ConflictOverrideModal'
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css'
import '../Gantt/gantt.css'
import './resourceView.css'

interface Props {
  scale?: 'day' | 'week' | 'month'
  onPhaseClick: (phaseId: number) => void
  /** 父级冲突版本号（热力图/报告消除后 bump → 本视图重建，跨视图同步——用户问题 2） */
  conflictVersion?: number
  /** 本视图消除成功后通知父级 bump（热力图/报告同步刷新） */
  onConflictChanged?: () => void
}

/**
 * 资源负载视图：多行甘特图，每人一行。
 *
 * 数据组织：每个人作为一个"项目"行（type=project），其参与的阶段作为子任务（type=task）。
 * 这样 dhtmlxGantt 天然呈现"每人一行，行内显示其阶段"的布局。
 *
 * 人员行 id 用负数（-personId），阶段行 id 用 phase_id（正数），避免冲突。
 */
export default function ResourceView({ scale = 'week', onPhaseClick, conflictVersion = 0, onConflictChanged }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const ganttRef = useRef<any>(null)
  const scaleRef = useRef(scale)
  scaleRef.current = scale

  // 冲突消除（CONFLICT_MODEL_V2 §2.4 决策 ③）：黄框冲突条点击 → 消除弹窗
  // 仅 admin/manager；非冲突条/无权限维持原行为（打开阶段详情）
  const [overrideTarget, setOverrideTarget] = useState<OverrideTarget | null>(null)
  const [reloadFlag, setReloadFlag] = useState(0)
  const canOverrideRef = useRef(false)
  // "resourceId:phaseId" → 消除目标（该资源该阶段所属冲突对）
  const pairMapRef = useRef(new Map<string, OverrideTarget>())
  const viewPhaseRef = useRef<number | null>(null)

  useEffect(() => {
    getMe()
      .then((u) => { canOverrideRef.current = u.role === 'admin' || u.role === 'manager' })
      .catch(() => {})
  }, [])

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

        // 负载视图：左侧栏仅保留阶段名和工期，不显示负责人和开始时间
        gantt.config.columns = [
          { name: 'text', label: '阶段', width: 280, tree: true },
          { name: 'duration', label: '工期', width: 100, align: 'center' },
        ]

        // 负载视图：禁用所有编辑交互，仅查看
        gantt.config.drag_move = false
        gantt.config.drag_resize = false
        gantt.config.drag_progress = false
        gantt.config.drag_links = false
        // 禁用右键菜单（防止误删除连线等操作）
        gantt.config.touch = false
        gantt.config.order_branch = false

        // 加载全员负载数据 + 资源冲突（冲突阶段打黄色标记）
        const [allWorkloads, conflicts] = await Promise.all([
          getAllWorkloads(),
          getResourceConflicts(),
        ])
        if (destroyed) return

        // phase_id 按资源视角的冲突描述（用户问题 2：黄框只标"该资源视角"的冲突对
        // 成员——共担者行里的阶段即使参与他人冲突对也不标黄，与热力图 ⚠ 口径一致）
        const conflictMap = new Map<string, string>()
        // "resourceId:phaseId" → 消除目标（v2.1 按阶段：点击冲突条消除该甘特条）
        const pairMap = pairMapRef.current
        pairMap.clear()
        for (const rc of conflicts) {
          for (const c of rc.conflicts) {
            const desc = `与 ${c.project_b_name}·${c.phase_b_name} 重叠 ${c.overlap_days} 天`
            conflictMap.set(`${rc.resource_id}:${c.phase_a_id}`, [conflictMap.get(`${rc.resource_id}:${c.phase_a_id}`), desc].filter(Boolean).join('；'))
            const descB = `与 ${c.project_a_name}·${c.phase_a_name} 重叠 ${c.overlap_days} 天`
            conflictMap.set(`${rc.resource_id}:${c.phase_b_id}`, [conflictMap.get(`${rc.resource_id}:${c.phase_b_id}`), descB].filter(Boolean).join('；'))
            // 消除目标按阶段：同一阶段可能参与多个对，只存一份（消除即剔除该阶段）
            if (!pairMap.has(`${rc.resource_id}:${c.phase_a_id}`)) {
              pairMap.set(`${rc.resource_id}:${c.phase_a_id}`, {
                resourceId: rc.resource_id,
                resourceName: rc.resource_name,
                phaseId: c.phase_a_id,
                summary: `${c.project_a_name}·${c.phase_a_name}`,
              })
            }
            if (!pairMap.has(`${rc.resource_id}:${c.phase_b_id}`)) {
              pairMap.set(`${rc.resource_id}:${c.phase_b_id}`, {
                resourceId: rc.resource_id,
                resourceName: rc.resource_name,
                phaseId: c.phase_b_id,
                summary: `${c.project_b_name}·${c.phase_b_name}`,
              })
            }
          }
        }

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

          // 该人员冲突阶段数（人员行角标）——按资源视角
          const conflictCount = wl.workloads.filter((w) => conflictMap.has(`${wl.resource.id}:${w.phase_id}`)).length

          // 人员行（type=project，显示姓名 + 阶段数）
          tasks.push({
            id: personRowId,
            text: `${wl.resource.name}${wl.resource.role ? '（' + wl.resource.role + '）' : ''}${conflictCount > 0 ? ` ⚠️${conflictCount}` : ''}`,
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
            const conflictInfo = conflictMap.get(`${wl.resource.id}:${w.phase_id}`)
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
              resource_id: wl.resource.id, // 冲突条消除定位用（resource × 阶段对）
              phase_id: w.phase_id, // 真实阶段 id，点击时取这个
              conflict_info: conflictInfo, // 冲突描述（有值 → 黄色标记 + tooltip）
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
              // 冲突条 + admin/manager → 弹消除 Modal（决策 ③）；其余维持原行为
              const target = canOverrideRef.current && task.conflict_info
                ? pairMapRef.current.get(`${task.resource_id}:${task.phase_id}`)
                : undefined
              if (target) {
                viewPhaseRef.current = task.phase_id
                setOverrideTarget(target)
                return
              }
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
    // reloadFlag：消除成功后重建甘特（冲突条黄框消失）；conflictVersion：跨视图同步（用户问题 2）
  }, [reloadFlag, conflictVersion])

  // 尺度切换
  useEffect(() => {
    if (ganttRef.current) {
      setScale(ganttRef.current, scale)
      if (containerRef.current) {
        setTimeout(() => drawTodayMarker(ganttRef.current, containerRef.current!), 0)
      }
    }
  }, [scale])

  return (
    <>
      <div ref={containerRef} className="pm-gantt-container resource-view" style={{ width: '100%', height: '70vh' }} />
      <ConflictOverrideModal
        target={overrideTarget}
        open={overrideTarget !== null}
        onClose={() => setOverrideTarget(null)}
        onOverridden={() => {
          // 本视图消除成功 → 通知父级 bump（热力图/报告同步刷新，用户问题 2）
          onConflictChanged?.()
          setReloadFlag((v) => v + 1) // 本地兜底重建甘特（黄框消失）
        }}
        onViewPhase={() => {
          const pid = viewPhaseRef.current
          setOverrideTarget(null)
          if (pid) onPhaseClick(pid)
        }}
      />
    </>
  )
}

function fmt(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 今日标记由共享 drawTodayMarker 绘制（见 ../Gantt/todayMarker.ts）
