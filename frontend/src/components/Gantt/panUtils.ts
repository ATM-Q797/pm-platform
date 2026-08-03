/**
 * 空白处拖动平移：在时间轴空白区按住左键拖动，实现左右平移。
 * 点甘特条/连线等可交互元素时不触发（交给 dhtmlx 的拖拽改期）。
 * 必须在 gantt.init() 之后调用（此时 .gantt_data_area DOM 已存在）。
 *
 * 从 GanttChart.tsx 抽出，供 GanttChart 和 ResourceView 复用。
 */
let _panCleanup: (() => void) | null = null

export function cleanupPan() {
  if (_panCleanup) {
    _panCleanup()
    _panCleanup = null
  }
}

export function setupPan(gantt: any, container: HTMLElement) {
  // 先清理上次的监听（scale 切换重建/组件切换时会重复调用）
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
    if (
      target.closest(
        '.gantt_task_line, .gantt_task_link, .gantt_link_arrow_right, .gantt_link_arrow_left, .gantt_task_progress_drag, .pm-today-marker'
      )
    ) {
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
    // 拖动平移后阻止紧随的 click（避免误触发点击）
    if (panMoved) e.stopPropagation()
  }

  dataArea.addEventListener('mousedown', onMouseDown, true) // capture 阶段，先于 dhtmlx 捕获
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
