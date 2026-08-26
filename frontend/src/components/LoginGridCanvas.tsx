import { useEffect, useRef } from 'react'
import { useTheme } from '../theme'

/**
 * 登录页全屏动态网格 Canvas：三层正弦叠加波浪涌动。
 * 零依赖；不做 prefers-reduced-motion 降级（产品核心动效，2026-08-26 用户要求）。
 * 2026-08-26：按用户要求删除指针扰动，增强波浪速度与幅度。
 */

const SPACING = 32 // 网格间距 px
const STEP = 10 // 曲线采样步长 px
const BASE_AMP = 10 // 基础振幅 px（原 6，增强感知度）

/** 三层正弦叠加位移场（避免死板单向流动；时间系数原 0.9/0.53/1.31 → 提速 ~1.5×） */
function waveOffset(x: number, y: number, t: number): number {
  return (
    BASE_AMP * 0.55 * Math.sin(0.021 * x + 0.017 * y + t * 1.35) +
    BASE_AMP * 0.3 * Math.sin(0.013 * x - 0.023 * y + t * 0.8) +
    BASE_AMP * 0.15 * Math.sin(0.031 * x + 0.008 * y - t * 1.95)
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

    let w = 0
    let h = 0
    let raf = 0
    let lastFrame = 0

    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // canvas.width 赋值会清空位图，下一帧 rAF 自动重绘
    }

    /** 采样点位移 = 波浪场（x/y 换相位，避免同步） */
    const displace = (x: number, y: number, t: number): [number, number] => [
      waveOffset(x, y, t),
      waveOffset(y + 137.3, x - 71.7, t),
    ]

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h)
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      for (let y = 0; y <= h + SPACING; y += SPACING) {
        for (let x = 0; x <= w + STEP; x += STEP) {
          const [ox, oy] = displace(x, y, t)
          if (x === 0) ctx.moveTo(x + ox, y + oy)
          else ctx.lineTo(x + ox, y + oy)
        }
      }
      for (let x = 0; x <= w + SPACING; x += SPACING) {
        for (let y = 0; y <= h + STEP; y += STEP) {
          const [ox, oy] = displace(x, y, t)
          if (y === 0) ctx.moveTo(x + ox, y + oy)
          else ctx.lineTo(x + ox, y + oy)
        }
      }
      ctx.stroke()
    }

    resize() // 初始尺寸（首帧由 rAF 绘制）

    const loop = (now: number) => {
      raf = requestAnimationFrame(loop)
      const dt = now - lastFrame
      lastFrame = now
      if (dt > 50) return // 降频保护：后台/卡顿帧跳过绘制
      draw(now / 1000)
    }
    raf = requestAnimationFrame(loop)

    window.addEventListener('resize', resize)

    return () => {
      cancelAnimationFrame(raf)
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
