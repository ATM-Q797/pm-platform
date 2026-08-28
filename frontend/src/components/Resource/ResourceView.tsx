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
  // 初始加载 + 外部强制刷新入口（reloadFlag 目前仅初始为 0；消除冲突走局部更新，不重建——用户 2026-08-28）
  const [reloadFlag] = useState(0)
  const canOverrideRef = useRef(false)
  // "resourceId:phaseId" → 消除目标（该资源该阶段所属冲突对）
  const pairMapRef = useRef(new Map<string, OverrideTarget>())
  // "resourceId:phaseId" → 冲突描述（局部更新用，消除后不重建甘特——用户 2026-08-28）
  const conflictMapRef = useRef(new Map<string, string>())
  const viewPhaseRef = useRef<number | null>(null)
  const conflictVersionFirstRun = useRef(true)

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
        conflictMapRef.current = conflictMap

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

          // 该人员冲突阶段数（人员行角标）——按资源视角（P8 已由后端 /all/workload 排除）
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
            open: false, // 人员负载行默认折叠，点击展开显示阶段（用户 2026-08-28）
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
    // reloadFlag：强制重建（初始加载）；消除冲突后走下方局部更新，不重建（用户 2026-08-28）
  }, [reloadFlag])

  // 冲突变化（本页消除 / 审核中心撤销 / 其他视图）→ 局部更新冲突标记：
  // 重拉 /conflicts → 只刷新受影响的任务条与人员行角标，保留滚动位置与展开状态
  useEffect(() => {
    if (conflictVersionFirstRun.current) {
      conflictVersionFirstRun.current = false
      return
    }
    let cancelled = false
    getResourceConflicts()
      .then((conflicts) => {
        if (cancelled) return
        const g = ganttRef.current
        if (!g || !g.getTask) return
        // 重建冲突映射（pairMap 供点击消除定位；conflictMap 供黄框标记）
        const conflictMap = conflictMapRef.current
        conflictMap.clear()
        const pairMap = pairMapRef.current
        pairMap.clear()
        for (const rc of conflicts) {
          for (const c of rc.conflicts) {
            const desc = `与 ${c.project_b_name}·${c.phase_b_name} 重叠 ${c.overlap_days} 天`
            conflictMap.set(`${rc.resource_id}:${c.phase_a_id}`, [conflictMap.get(`${rc.resource_id}:${c.phase_a_id}`), desc].filter(Boolean).join('；'))
            const descB = `与 ${c.project_a_name}·${c.phase_a_name} 重叠 ${c.overlap_days} 天`
            conflictMap.set(`${rc.resource_id}:${c.phase_b_id}`, [conflictMap.get(`${rc.resource_id}:${c.phase_b_id}`), descB].filter(Boolean).join('；'))
            if (!pairMap.has(`${rc.resource_id}:${c.phase_a_id}`)) {
              pairMap.set(`${rc.resource_id}:${c.phase_a_id}`, {
                resourceId: rc.resource_id, resourceName: rc.resource_name,
                phaseId: c.phase_a_id, summary: `${c.project_a_name}·${c.phase_a_name}`,
              })
            }
            if (!pairMap.has(`${rc.resource_id}:${c.phase_b_id}`)) {
              pairMap.set(`${rc.resource_id}:${c.phase_b_id}`, {
                resourceId: rc.resource_id, resourceName: rc.resource_name,
                phaseId: c.phase_b_id, summary: `${c.project_b_name}·${c.phase_b_name}`,
              })
            }
          }
        }
        // 阶段行：更新 conflict_info（黄框/tooltip）
        for (const t of g.getAllTask()) {
          if (Number(t.id) > 0 && t.resource_id != null) {
            const info = conflictMap.get(`${t.resource_id}:${t.phase_id}`)
            if (t.conflict_info !== info) {
              t.conflict_info = info
              g.refreshTask(t.id)
            }
          }
        }
        // 人员行：⚠️N 角标
        const counts = new Map<number, number>()
        for (const t of g.getAllTask()) {
          if (Number(t.id) > 0 && t.resource_id != null && t.conflict_info) {
            counts.set(t.resource_id, (counts.get(t.resource_id) || 0) + 1)
          }
        }
        for (const t of g.getAllTask()) {
          if (Number(t.id) < 0) {
            const n = counts.get(-Number(t.id)) || 0
            const base = String(t.text).replace(/\s*⚠️\d*$/, '')
            const text = n > 0 ? `${base} ⚠️${n}` : base
            if (t.text !== text) {
              t.text = text
              g.refreshTask(t.id)
            }
          }
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [conflictVersion])

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
          // 本视图消除成功 → 父级 bump（conflictVersion → 本页局部更新 + 热力图/审核中心同步）
          onConflictChanged?.()
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
