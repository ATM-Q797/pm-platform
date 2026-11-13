import { useEffect, useRef } from 'react'

interface Star {
  x: number
  y: number
  r: number
  base: number
  phase: number
  speed: number
}

/* 动态星空层（Canvas）——叠加在真实壁纸之上（登录页恒深色，2026-11-13 用户裁定）。
   借鉴 CSDN《纯 HTML+CSS+JS 实现高颜值星空登录注册页面教程》的动态星星层做法：
   每颗星随机位置/大小/闪烁节奏（相位 + 速度错开避免同步闪）。
   **恒动**：不设 prefers-reduced-motion 降级——用户 2026-11-13 裁定「星空动效即登录页主体视觉」
   （用户环境系统级减动效曾致星光静止），特例豁免已入批档；流星已按用户裁定移除。 */
export default function LoginStarfield() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const STAR_COUNT = 150

    let w = 0
    let h = 0
    let stars: Star[] = []
    let raf = 0

    const resize = () => {
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = Math.max(1, Math.round(w * dpr))
      canvas.height = Math.max(1, Math.round(h * dpr))
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      stars = Array.from({ length: STAR_COUNT }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.3 + 0.5,
        base: Math.random() * 0.44 + 0.22,
        phase: Math.random() * Math.PI * 2,
        speed: Math.random() * 0.0022 + 0.0006,
      }))
    }

    const draw = (now: number) => {
      ctx.clearRect(0, 0, w, h)

      for (const s of stars) {
        const alpha = s.base + 0.45 * Math.sin(now * s.speed + s.phase)
        ctx.globalAlpha = Math.min(1, Math.max(0, alpha))
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
        ctx.fillStyle = '#ffffff'
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    const loop = (now: number) => {
      draw(now)
      raf = requestAnimationFrame(loop)
    }

    resize()
    window.addEventListener('resize', resize)
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={ref} className="neu-starfield" aria-hidden="true" />
}
