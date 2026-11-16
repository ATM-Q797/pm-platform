/** prefers-reduced-motion 检测（动效批）：reduced-motion 下弹窗走 transitionName 空名短路
 *  （@rc-component/motion isSupportTransition 对空 motionName 直接 false、零等待），不用 CSS 零时长动画
 *  （2026-08-26 教训：零时长 animationend 不触发会挂死 rc-motion）。 */
export default function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
