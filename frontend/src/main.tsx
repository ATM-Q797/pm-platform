import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App.tsx'

dayjs.locale('zh-cn')

// 注意：不使用 StrictMode。dhtmlxGantt 是全局单例命令式库，
// StrictMode 的 useEffect 双调用会破坏 gantt 单例初始化。
createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </ErrorBoundary>
)
