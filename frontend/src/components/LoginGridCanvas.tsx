import { useEffect, useRef } from 'react'
import { useTheme } from '../theme'

/**
 * 登录页全屏动态网格 Canvas：波浪涌动 + 指针扰动 + 速度感知。
 * 零依赖；reduced-motion 下只画一帧静态网格。
 */

const SPACING = 32 // 网格间距 px
const STEP = 10 // 曲线采样步长 px
const BASE_AMP = 6 // 基础振幅 px
const SIGMA = 160 // 指针扰动高斯衰减 σ
const G0 = 26 // 指针扰动基准强度 px
const V0 = 3 // 速度感知基准 v0（px/帧），中速移动落入 0.6-3× 中间区

/** 三层正弦叠加位移场（避免死板单向流动） */
function waveOffset(x: number, y: number, t: number): number {
  return (
    BASE_AMP * 0.55 * Math.sin(0.021 * x + 0.017 * y + t * 0.9) +
    BASE_AMP * 0.3 * Math.sin(0.013 * x - 0.023 * y + t * 0.53) +
    BASE_AMP * 0.15 * Math.sin(0.031 * x + 0.008 * y - t * 1.31)
  )
}

export default function LoginGridCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { mode } = useTheme()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const color =
      mode === 'dark' ? 'rgba(0,212,255,.06)' : 'rgba(8,145,178,.06)'
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let w = 0
    let h = 0
    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // canvas.width 赋值会清空位图；reduced-motion 无 rAF，需手动重绘静态帧
      if (reduced) draw(0, BASE_AMP)
    }

    // 指针状态
    let px = 0
    let py = 0
    let hasPointer = false
    let pointerActive = 0 // 离开窗口后平滑衰减到 0
    let speed = 0 // 指数平滑后的指针速度
    let lastT = 0
    let raf = 0
    let lastFrame = 0

    const onPointer = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return // 触屏纯涌动，不驱动扰动
      const now = performance.now()
      if (hasPointer && now - lastT > 0) {
        const inst = Math.hypot(e.clientX - px, e.clientY - py) /
          ((now - lastT) / 16.7) // 折算为 px/帧
        speed += (inst - speed) * 0.2 // 指数平滑
      }
      px = e.clientX
      py = e.clientY
      lastT = now
      hasPointer = true
      pointerActive = 1
    }
    const onLeave = () => {
      hasPointer = false
    }
    window.addEventListener('pointermove', onPointer, { passive: true })
    window.addEventListener('pointerdown', onPointer, { passive: true })
    window.addEventListener('pointerup', onLeave, { passive: true })
    window.addEventListener('pointercancel', onLeave, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave, { passive: true })
    window.addEventListener('resize', resize)

    /** 采样点的总位移 = 波浪场 + 指针高斯扰动（向外推开） */
    const displace = (x: number, y: number, t: number, amp: number): [number, number] => {
      const s = amp / BASE_AMP // 速度感知缩放同时作用于波浪振幅
      const ox = waveOffset(x, y, t) * s
      const oy = waveOffset(y + 137.3, x - 71.7, t) * s // 换相位，xy 不同步
      let dx = 0
      let dy = 0
      if (pointerActive > 0.001) {
        const ddx = x - px
        const ddy = y - py
        const d2 = ddx * ddx + ddy * ddy
        // 扰动强度按 (1+s) 而非 amp 缩放，避免快速移动时网格线互相穿透
        const f = G0 * (1 + s) * pointerActive * Math.exp(-d2 / (SIGMA * SIGMA))
        const d = Math.sqrt(d2) || 1
        dx = (ddx / d) * f
        dy = (ddy / d) * f
      }
      return [ox + dx, oy + dy]
    }

    const draw = (t: number, amp: number) => {
      ctx.clearRect(0, 0, w, h)
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      for (let y = 0; y <= h + SPACING; y += SPACING) {
        for (let x = 0; x <= w + STEP; x += STEP) {
          const [ox, oy] = displace(x, y, t, amp)
          if (x === 0) ctx.moveTo(x + ox, y + oy)
          else ctx.lineTo(x + ox, y + oy)
        }
      }
      for (let x = 0; x <= w + SPACING; x += SPACING) {
        for (let y = 0; y <= h + STEP; y += STEP) {
          const [ox, oy] = displace(x, y, t, amp)
          if (y === 0) ctx.moveTo(x + ox, y + oy)
          else ctx.lineTo(x + ox, y + oy)
        }
      }
      ctx.stroke()
    }

    resize() // 初始尺寸 + reduced 静态帧（须在 draw 定义之后调用）

    if (reduced) {
      draw(0, BASE_AMP) // 静态一帧，不启动 rAF
    } else {
      const loop = (now: number) => {
        raf = requestAnimationFrame(loop)
        const dt = now - lastFrame
        lastFrame = now
        if (dt > 50) return // 降频保护：后台/卡顿帧跳过绘制
        // 指针离开后 0.5s 平滑衰减归零（约 30 帧）
        if (!hasPointer) pointerActive = Math.max(0, pointerActive - 0.033)
        speed *= 0.98 // 静止时速度自然回落
        const scale = Math.min(3, Math.max(0.6, speed / V0))
        draw(now / 1000, BASE_AMP * scale)
      }
      raf = requestAnimationFrame(loop)
    }

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onPointer)
      window.removeEventListener('pointerdown', onPointer)
      window.removeEventListener('pointerup', onLeave)
      window.removeEventListener('pointercancel', onLeave)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('resize', resize)
    }
  }, [mode]) // 主题切换时重绘取色

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  )
}
