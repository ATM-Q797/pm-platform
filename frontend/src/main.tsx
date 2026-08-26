import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App.tsx'
import { ThemeProvider, useTheme } from './theme.tsx'
import './index.css'
import './styles/tech.css' // 科技感视觉层（须在 index.css 之后）

dayjs.locale('zh-cn')

// 主题化应用外壳：按当前模式切换 AntD 算法
function ThemedApp() {
  const { mode } = useTheme()
  const isDark = mode === 'dark'
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          // 色值以 docs/UI_TECH_STYLE.md §二 为权威；浅色主色 #0369a1 保证对比度 ≥4.5:1
          colorPrimary: isDark ? '#00d4ff' : '#0369a1',
          colorInfo: isDark ? '#00d4ff' : '#0369a1',
          colorLink: isDark ? '#00d4ff' : '#0369a1',
          colorSuccess: isDark ? '#22e58a' : '#16a34a',
          colorError: isDark ? '#ff4d6d' : '#e11d48',
          colorWarning: isDark ? '#fbbf24' : '#b45309',
          borderRadius: 10,
          colorBgLayout: isDark ? '#0a0e1a' : '#eef2f8',
          colorBgContainer: isDark ? 'rgba(20,27,45,.72)' : 'rgba(255,255,255,.8)',
          colorBgElevated: isDark ? '#141b2d' : '#ffffff',
          colorBorder: isDark ? 'rgba(120,180,255,.15)' : 'rgba(8,145,178,.15)',
          boxShadowTertiary: '0 0 0 1px rgba(0,212,255,.08), 0 8px 24px rgba(0,0,0,.25)',
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: { headerBg: 'transparent', headerHeight: 56, headerPadding: '0 24px', siderBg: 'transparent' },
          Menu: {
            darkItemBg: 'transparent',
            itemSelectedBg: isDark ? 'rgba(0,212,255,.12)' : 'rgba(3,105,161,.1)',
            itemSelectedColor: isDark ? '#00d4ff' : '#0369a1',
            itemHoverBg: isDark ? 'rgba(0,212,255,.08)' : 'rgba(3,105,161,.06)',
            darkItemHoverBg: 'rgba(0,212,255,.08)',
            activeBarHeight: 3,
          },
          Card: {
            paddingLG: 20,
            colorBgContainer: isDark ? 'rgba(20,27,45,.55)' : 'rgba(255,255,255,.75)',
          },
          Table: {
            // 列表行用实色（性能红线：半透明/blur 仅限卡片视觉层）
            headerBg: isDark ? 'rgba(15,20,36,.9)' : 'rgba(240,246,252,.9)',
            rowHoverBg: isDark ? 'rgba(0,212,255,.06)' : 'rgba(3,105,161,.05)',
            colorBgContainer: isDark ? '#0f1424' : '#ffffff',
          },
          Input: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
          },
          // Select/DatePicker 与 Input 一致实色（半透明仅限卡片视觉层）
          Select: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
          },
          DatePicker: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
          },
          Button: { primaryShadow: isDark ? '0 0 12px rgba(0,212,255,.35)' : '0 0 12px rgba(3,105,161,.25)' },
          Tag: { borderRadiusSM: 4 },
          Segmented: { itemSelectedBg: isDark ? 'rgba(0,212,255,.15)' : 'rgba(3,105,161,.12)' },
          // 浮层实色 token（半透明仅限卡片视觉层，避免 alpha 叠加导致对比度不可控）
          Modal: { contentBg: isDark ? '#141b2d' : '#ffffff' },
          Drawer: { colorBgElevated: isDark ? '#141b2d' : '#ffffff' },
          Popover: { colorBgElevated: isDark ? '#141b2d' : '#ffffff' },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  )
}

// 注意：不使用 StrictMode。dhtmlxGantt 是全局单例命令式库，
// StrictMode 的 useEffect 双调用会破坏 gantt 单例初始化。
createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  </ErrorBoundary>
)
