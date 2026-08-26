/**
 * 自绘"今天"标记 — 项目甘特图与资源负载图共享。
 *
 * 挂载于 .gantt_task（时间轴可视区背景层）顶部：随横向滚动、不随纵向滚动，
 * 冻结在今日日期刻度位置。样式见 gantt.css（.pm-today-marker / .pm-today-label）。
 */
export function drawTodayMarker(gantt: any, container: HTMLElement) {
  container.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())

  const taskArea = container.querySelector('.gantt_task') as HTMLElement | null
  if (!taskArea) return

  // 清除旧标记（taskArea 内）
  taskArea.querySelectorAll('.pm-today-marker').forEach((el) => el.remove())

  const x = gantt.posFromDate(new Date())
  if (typeof x !== 'number' || isNaN(x)) return

  const marker = document.createElement('div')
  marker.className = 'pm-today-marker'
  marker.style.cssText = `position:absolute;left:${x}px;top:2px;z-index:10;pointer-events:none;white-space:nowrap;`

  const label = document.createElement('span')
  label.textContent = '今天'
  label.className = 'pm-today-label'

  marker.appendChild(label)
  taskArea.appendChild(marker)
}
