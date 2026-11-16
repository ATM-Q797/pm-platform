/** prefers-reduced-motion 检测（动效批）：reduced-motion 下弹窗直接开合走 motion={null} 分支，
 *  不用 CSS 零时长动画（tech.css 降级注 2026-08-26 教训：零时长 animationend 不触发会挂死 rc-motion）。 */
export default function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
