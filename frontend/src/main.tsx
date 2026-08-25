import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App.tsx'
import './index.css'

dayjs.locale('zh-cn')

// 注意：不使用 StrictMode。dhtmlxGantt 是全局单例命令式库，
// StrictMode 的 useEffect 双调用会破坏 gantt 单例初始化。
createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 8,
          colorBgLayout: '#f5f7fa',
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: { headerBg: '#001529', headerHeight: 56, headerPadding: '0 24px' },
          Menu: { darkItemBg: '#001529' },
          Card: { paddingLG: 20 },
          Table: { headerBg: '#fafbfc', rowHoverBg: '#f0f7ff' },
          Segmented: { itemSelectedBg: '#e6f4ff' },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </ErrorBoundary>
)
