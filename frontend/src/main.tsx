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
import './styles/neu.css' // 拟态视觉层（须在 tech.css 之后）

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
          // 控件高 28px：用户 2026-11-14「所有输入框的高度再缩减一点」+ v4 样张批准（输入/钮同尺紧凑 macOS 比例）——直取
          controlHeight: 28,
          // 地面层透明：地面渐变+极光由 index.css html 画布层直绘——v4 快照透感 = 面板透出地面；
          // 不透明 token 会盖死极光（对表修齐 2026-11-14）；浮层壳 = 高不透明玻璃档（B 案）由 glass.css 8.6 承面，
          // 下拉/Popover/Popconfirm 沿实色（面板走全局 colorBgElevated 实色）
          colorBgLayout: 'transparent',
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
            itemSelectedBg: isDark ? 'rgba(0,212,255,.12)' : 'rgba(3,105,161,.12)',
            itemSelectedColor: isDark ? '#00d4ff' : '#0369a1',
            itemHoverBg: isDark ? 'rgba(0,212,255,.1)' : 'rgba(3,105,161,.1)',
            darkItemHoverBg: 'rgba(0,212,255,.1)',
            activeBarHeight: 3,
          },
          Card: {
            paddingLG: 20,
            colorBgContainer: isDark ? 'rgba(20,27,45,.55)' : 'rgba(255,255,255,.75)',
          },
          Table: {
            // 表头 = 半透明底 + 高光线模拟（glass.css 8.9；滚动区豁免 blur——性能红线）
            // 表身 = 容器 .8 白 token 面（随全局 colorBgContainer；docs/UI_TECH_STYLE.md 1.4 三件保留②「保行文可读，非全透」）
            headerBg: isDark ? 'rgba(15,20,36,.65)' : 'rgba(240,246,252,.65)',
            rowHoverBg: isDark ? 'rgba(0,212,255,.06)' : 'rgba(3,105,161,.05)',
          },
          Input: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
            // 占位符对比度收口（台账 #20，组件 token 覆盖）：值直取 docs/UI_TECH_STYLE.md 1.2「文字 Secondary」——
            // 浅 #475569 对拟态凹陷面最深角 #cacaca 4.68:1（原 antd 预设仅 1.83:1）；深 #9aa3b8 对面 #2e3339 5.04:1
            colorTextPlaceholder: isDark ? '#9aa3b8' : '#475569',
          },
          InputNumber: {
            // 占位符同 Input 口径（台账 #20；值直取 1.2 文字 Secondary）
            colorTextPlaceholder: isDark ? '#9aa3b8' : '#475569',
          },
          // Select/DatePicker 与 Input 一致实色（B 案口径：下拉/Popover/Popconfirm 文字密集小件沿实色 token）
          Select: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
            // 下拉面板实色钉值（B 案：文字密集小件沿实色；面板面底随全局 colorBgElevated，此处显式钉防漂）
            colorBgElevated: isDark ? '#141b2d' : '#ffffff',
            // 占位符同 Input 口径（台账 #20；值直取 1.2 文字 Secondary）
            colorTextPlaceholder: isDark ? '#9aa3b8' : '#475569',
          },
          // Dropdown 面板实色同钉（下拉菜单文字密集，B 案沿实色）
          Dropdown: {
            colorBgElevated: isDark ? '#141b2d' : '#ffffff',
          },
          DatePicker: {
            colorBgContainer: isDark ? '#141b2d' : '#ffffff',
            // 占位符同 Input 口径（台账 #20；值直取 1.2 文字 Secondary）
            colorTextPlaceholder: isDark ? '#9aa3b8' : '#475569',
          },
          // Button 影调已归拟态双影（UI批3：primary 保留 accent 面、影色随 accent 同构，五态在 neu.css 8 段）——
          // 原 primaryShadow 发光影值随发光材质退场（UI_TECH_STYLE 用户裁定注记 1），不再单设组件 token
          Tag: {
            borderRadiusSM: 4,
            // 预设状态 Tag 文字色对比度收口（台账 #20，组件 token 覆盖）：值直取 neu.css 1b 文字级语义色
            // （原 antd 预设语义色作小字仅 2.47-4.26:1；收口后浅色 ≥4.5:1，深色同值记册）；
            // 危险色下沉一档 #be123c（5.7:1）——#e11d48 对 Tag 实色底 #fff2f0 仅 4.31:1，小字过线为准（1b 同法）
            colorSuccess: isDark ? '#22e58a' : '#15803d',
            colorError: isDark ? '#ff4d6d' : '#be123c',
            colorWarning: isDark ? '#fbbf24' : '#b45309',
            colorInfo: isDark ? '#00d4ff' : '#0369a1',
            // 预设底色收口（仅浅色）：antd v6 预设底 = 语义色淡混实色，自吃对比度（实测 3.76-4.26:1）——
            // 收口为经典实色 tint 档（#f6ffed/#e6f4ff/#fff2f0/#fffbe6，antd 预设 tint 同源）；深色保留 antd 派生底（记册）
            ...(isDark
              ? {}
              : {
                  colorSuccessBg: '#f6ffed',
                  colorInfoBg: '#e6f4ff',
                  colorErrorBg: '#fff2f0',
                  colorWarningBg: '#fffbe6',
                }),
          },
          Segmented: { itemSelectedBg: isDark ? 'rgba(0,212,255,.15)' : 'rgba(3,105,161,.12)' },
          // Tabs 选中项 accent 文字色（glass.css 8.8 玻璃凸起胶囊；ink-bar 隐藏同处承）
          Tabs: { itemSelectedColor: isDark ? '#00d4ff' : '#0369a1' },
          // 浮层壳 = 高不透明玻璃档（B 案，用户 2026-11-15）：Modal/Drawer 壳面材 .8 档（blur/亮边/顶光由 glass.css 8.6 承）；
          // 下拉/Popover/Popconfirm 文字密集小件沿实色 token（Select/Dropdown 面板实色已钉）
          Modal: { contentBg: isDark ? 'rgba(20,27,45,.8)' : 'rgba(255,255,255,.8)' },
          Drawer: { colorBgElevated: isDark ? 'rgba(20,27,45,.8)' : 'rgba(255,255,255,.8)' },
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
