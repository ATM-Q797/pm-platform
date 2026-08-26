import { createContext, useContext, useEffect, useState } from 'react'

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

  const toggle = () => setMode((m) => (m === 'light' ? 'dark' : 'light'))

  return <ThemeContext.Provider value={{ mode, toggle }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
