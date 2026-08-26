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
          colorPrimary: '#1677ff',
          borderRadius: 8,
          colorBgLayout: isDark ? '#0f1115' : '#f5f7fa',
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: { headerBg: '#001529', headerHeight: 56, headerPadding: '0 24px' },
          Menu: { darkItemBg: '#001529' },
          Card: { paddingLG: 20 },
          Table: { headerBg: isDark ? '#16181d' : '#fafbfc', rowHoverBg: isDark ? '#1e2128' : '#f0f7ff' },
          Segmented: { itemSelectedBg: isDark ? '#1e2128' : '#e6f4ff' },
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
