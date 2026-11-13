import { createContext, useContext, useEffect, useState } from 'react'
import { flushSync } from 'react-dom'

export type ThemeMode = 'light' | 'dark'

interface ThemeContextValue {
  mode: ThemeMode
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextValue>({ mode: 'light', toggle: () => {} })

function initialMode(): ThemeMode {
  const saved = localStorage.getItem('pm-theme')
  if (saved === 'light' || saved === 'dark') return saved
  // 首次访问跟随系统偏好
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialMode)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
    localStorage.setItem('pm-theme', mode)
  }, [mode])

  const toggle = () => {
    const next: ThemeMode = mode === 'light' ? 'dark' : 'light'
    // 换肤提交：data-theme / localStorage / React 状态同步落（回调内完成，供 View Transitions 快照）
    const commit = () => {
      document.documentElement.setAttribute('data-theme', next)
      localStorage.setItem('pm-theme', next)
      setMode(next)
    }
    const vt = document as unknown as { startViewTransition?: (update: () => void) => void }
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (typeof vt.startViewTransition === 'function' && !reduce) {
      // 增强：View Transitions API 整页交叉淡变（docs/UI_REORG_PLAN.md 3.3）；回调内 flushSync 保证新态进快照
      vt.startViewTransition(() => flushSync(commit))
    } else {
      // 基线：tech.css 全局过渡行 0.25s 淡变；prefers-reduced-motion → 直接切换（降级纪律优先于过渡）
      commit()
    }
  }

  return <ThemeContext.Provider value={{ mode, toggle }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
