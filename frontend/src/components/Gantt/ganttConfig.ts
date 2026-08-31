// 平移中抑制浮窗（GANTT_REMARK_TOOLTIP v1.5 处置）：panUtils 不 import 本文件，无循环依赖
import { isPanning } from './panUtils'

// dhtmlxGantt 配置：列定义、状态着色、scale、返工标记
// 注意：gantt 实例由 GanttChart 动态 import 后传入，本文件不在顶层 import dhtmlx-gantt，
// 避免模块求值阶段触发 dhtmlx-gantt 加载导致白屏。

// 阶段状态 → CSS class（用于甘特条着色）
const STATUS_CLASS: Record<string, string> = {
  已完成: 'gantt-task-done',
  进行中: 'gantt-task-active',
  未开始: 'gantt-task-pending',
  延期: 'gantt-task-delayed',
  已搁置: 'gantt-task-blocked',
}

// 关键路径高亮：null = 关闭；Set<phase_id> = 高亮哪些阶段
let criticalHighlightIds: Set<number> | null = null

/** 设置关键路径高亮（null 关闭）。调用后需 gantt.render() 生效。 */
export function setCriticalHighlight(ids: Set<number> | null) {
  criticalHighlightIds = ids
}

// 用 any 接收 gantt 实例，避免顶层类型 import
type GanttInstance = any

// ---- 自定义 scale format 函数 ----
const CN_MONTH = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月']

// 上层：年月（如 "2026 年 六月"）
function monthFormat(date: Date): string {
  return `${date.getFullYear()} 年 ${CN_MONTH[date.getMonth()]}`
}

// 下层：当月第几周（每月从 1 重新计数，每月 1 号所在周为第 1 周）
function weekInMonthFormat(date: Date): string {
  const dayOfMonth = date.getDate() // 1-31
  const weekInMonth = Math.ceil(dayOfMonth / 7)
  return `第 ${weekInMonth} 周`
}

// 下层：日期数字（如 "17"，只显示数字）
function dayNumFormat(date: Date): string {
  return String(date.getDate())
}

// HTML 转义：备注原文按字面显示，不解析为标签（GANTT_REMARK_TOOLTIP §2.4，不引入第三方库）
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function applyGanttConfig(gantt: GanttInstance) {
  // 基础配置
  gantt.config.date_format = '%Y-%m-%d'
  gantt.config.row_height = 36
  gantt.config.bar_height = 22
  gantt.config.grid_width = 480
  gantt.config.autosize = false
  gantt.config.fit_tasks = true
  gantt.config.show_progress = true
  gantt.config.smart_rendering = true  // 虚拟渲染（性能红线：false 时滚动全量重建行 DOM，192 行实测 7 秒/帧）

  // 拖拽禁用（所有角色通过 PhaseEditor 窗口修改日期，避免误操作）
  gantt.config.drag_move = false
  gantt.config.drag_resize = false
  gantt.config.drag_progress = false

  // 禁用默认双击编辑器（由 PhaseEditor 抽屉替代）
  gantt.config.details_on_dblclick = false
  gantt.config.details_on_click = false

  // 依赖连线：显示并加粗；支持拖拽创建（悬停任务条两端圆形手柄拖到另一条）
  gantt.config.show_links = true
  gantt.config.drag_links = true
  gantt.config.link_line_width = 2.5
  gantt.config.link_arrow_size = 8

  // 左侧列定义
  gantt.config.columns = [
    { name: 'text', label: '阶段', width: 200, tree: true },
    // 负责人列：通过 template 渲染任务的 assignee_names 字段（在 GanttChart 里注入）
    { name: 'assignees', label: '负责人', width: 120, align: 'center',
      template: (task: any) => task.assignee_names || '' },
    { name: 'start_date', label: '开始', width: 90, align: 'center' },
    { name: 'duration', label: '工期', width: 60, align: 'center' },
  ]

  // 时间轴尺度：dhtmlxGantt 10.0 使用 gantt.config.scales（数组）。
  // 默认周尺度（2 层：上层年月，下层当月第几周）。详细配置在 setScale 里。
  gantt.config.scales = [
    { unit: 'month', step: 1, format: monthFormat },
    { unit: 'week', step: 1, format: weekInMonthFormat },
  ]

  // task_class：按状态着色 + 返工标记 + 关键路径高亮
  gantt.templates.task_class = function (_start: any, _end: any, task: any) {
    const classes: string[] = []
    if (task.type === 'task') {
      if (task.status && STATUS_CLASS[task.status]) {
        classes.push(STATUS_CLASS[task.status])
      }
      if (task.rework_count && task.rework_count > 0) {
        classes.push('gantt-task-rework')
      }
      // 关键路径（开关打开时）：红色粗边框，CSS 优先级高于返工标记
      if (criticalHighlightIds?.has(task.id)) {
        classes.push('gantt-task-critical')
      }
      // 资源冲突（资源视图）：黄色边框 + ⚠ 角标（浮窗已改为仅显示备注，冲突详情见条上角标与消除弹窗）
      if (task.conflict_info) {
        classes.push('gantt-task-conflict')
      }
    }
    return classes.join(' ')
  }

  // tooltip 插件（GANTT_REMARK_TOOLTIP §2.3）。顺序：先激活 tooltip 插件再设置超时值
  // （50ms，v1.3 用户要求）；plugins() 幂等，两视图重复调用安全（GanttChart 与 ResourceView 共用全局实例）
  gantt.plugins({ tooltip: true })
  gantt.config.tooltip_timeout = 50 // 悬停 50ms 即显示（GANTT_REMARK_TOOLTIP v1.4 验收 1）

  // tooltip：仅阶段行（type=task）且备注有效时显示转义后的备注原文（GANTT_REMARK_TOOLTIP §2.3）。
  // 返回 false → 不显示浮窗。项目行永不显示；纯空白备注不显示；
  // 资源负载视图的 task 带 resource_id（ResourceView 注入）→ 不显示（用户决策③：浮窗仅项目甘特图）。
  // 拖拽平移中（panUtils.isPanning）→ 不显示（v1.5 处置：平移中 dx≤3px 不滚动，onGanttScroll 隐藏不可靠）；
  // 依赖连线拖拽中 dhtmlx 内部已拦截 onBeforeTooltip。
  gantt.templates.tooltip_text = function (_start: any, _end: any, task: any) {
    if (isPanning()) return false // 拖拽平移中抑制浮窗（GANTT_REMARK_TOOLTIP v1.5 处置，验收 9b）
    if (task.type !== 'task') return false
    if (task.resource_id != null) return false
    if (typeof task.remark !== 'string' || task.remark.trim() === '') return false
    return escapeHtml(task.remark) // 原文不 trim：保留首尾空白/换行（GANTT_REMARK_TOOLTIP 验收 3e，处置 #3）
  }

  gantt.templates.task_row_class = function (_start: any, _end: any, task: any) {
    if (task.type === 'task' && task.status && STATUS_CLASS[task.status]) {
      return STATUS_CLASS[task.status]
    }
    return ''
  }

  // 中文 locale
  gantt.i18n.setLocale({
    date: {
      month_full: ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'],
      month_short: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
      day_full: ['星期日','星期一','星期二','星期三','星期四','星期五','星期六'],
      day_short: ['日','一','二','三','四','五','六'],
    },
    labels: {
      new_task: '新任务',
      icon_save: '保存',
      icon_cancel: '取消',
      icon_details: '详情',
      icon_edit: '编辑',
      icon_delete: '删除',
      confirm_closing: '',
      confirm_deleting: '任务将被删除，确定吗？',
      section_description: '描述',
      section_time: '时间',
      section_type: '类型',
      column_text: '阶段',
      column_start_date: '开始',
      column_duration: '工期',
      column_add: '',
      link: '链接',
      confirm_link_deleting: '将被删除',
      link_start: '（开始）',
      link_end: '（结束）',
      type_task: '任务',
      type_project: '项目',
      type_milestone: '里程碑',
      minutes: '分钟',
      hours: '小时',
      days: '天',
      weeks: '周',
      months: '月',
      years: '年',
    },
  })
}

// 切换时间轴尺度（dhtmlxGantt 10.0 的 scales 数组 API）
// 三种尺度的层级结构：
//   - 日：2 层，上层年月，下层日期数字（如 17）；甘特格子较小
//   - 周：2 层，上层年月，下层当月第几周（每月从 1 计数）
//   - 月：1 层，只显示年月
export function setScale(gantt: GanttInstance, level: 'day' | 'week' | 'month') {
  if (level === 'day') {
    // 日：上层年月 + 下层日期数字；格子变窄（min_column_width 小）
    gantt.config.scales = [
      { unit: 'month', step: 1, format: monthFormat },
      { unit: 'day', step: 1, format: dayNumFormat },
    ]
    gantt.config.min_column_width = 30   // 日格子窄
    gantt.config.scale_height = 60
  } else if (level === 'week') {
    // 周：上层年月 + 下层当月第几周
    gantt.config.scales = [
      { unit: 'month', step: 1, format: monthFormat },
      { unit: 'week', step: 1, format: weekInMonthFormat },
    ]
    gantt.config.min_column_width = 80   // 周格子正常
    gantt.config.scale_height = 50
  } else {
    // 月：只 1 层年月
    gantt.config.scales = [
      { unit: 'month', step: 1, format: monthFormat },
    ]
    gantt.config.min_column_width = 120  // 月格子宽
    gantt.config.scale_height = 36
  }
  // 切换尺度后强制重新渲染
  gantt.config.fit_tasks = true
  gantt.render()
}
