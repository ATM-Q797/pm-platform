import { useEffect, useState, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import { Layout, Menu, Spin, Dropdown, Space, Avatar, Button } from 'antd'
import {
  DashboardOutlined,
  ProjectOutlined,
  TeamOutlined,
  LogoutOutlined,
  KeyOutlined,
  DownOutlined,
  AuditOutlined,
  StarOutlined,
  MoonOutlined,
  SunOutlined,
  FormOutlined,
} from '@ant-design/icons'
import ErrorBoundary from './components/ErrorBoundary'
import LoginPage from './pages/LoginPage'
import ChangePasswordModal from './components/ChangePasswordModal'
import NotificationBell from './components/NotificationBell'
import DashboardPage from './pages/DashboardPage'
import ReportPage from './pages/ReportPage'
import { PROJECT_LIST_FILTERS_KEY as FILTERS_KEY, PROJECT_LIST_SEARCH_KEY as SEARCH_KEY, REPORT_FILTERS_KEY, REPORT_SEARCH_KEY } from './types'
import { getMe, logout } from './api/auth'
import { useTheme } from './theme'
import type { UserInfo } from './types'

// 懒加载详情页和资源页（含 GanttChart/dhtmlx-gantt），避免影响首页初始加载
const ProjectListPage = lazy(() => import('./pages/ProjectListPage'))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))
const MyTasksPage = lazy(() => import('./pages/MyTasksPage'))
const SpecialProjectsPage = lazy(() => import('./pages/SpecialProjectsPage'))
const AdminCenterPage = lazy(() => import('./pages/AdminCenterPage'))

const { Header, Content } = Layout


export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const { mode, toggle } = useTheme() // 深色/浅色模式
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [forcePwd, setForcePwd] = useState(false)

  // 刷新页面即重置列表筛选（用户 2026-10-26：返回列表不重置、刷新才重置）。
  // 列表筛选存 sessionStorage（ProjectListPage），刷新前在此统一清除——全站唯一入口，避免散落多处。
  // pagehide 兼容移动端/bfcache（评审 🟡#2），beforeunload 双保险，去重后同效。
  useEffect(() => {
    const clearListFilters = () => {
      try {
        sessionStorage.removeItem(FILTERS_KEY)
        sessionStorage.removeItem(SEARCH_KEY)
        sessionStorage.removeItem(REPORT_FILTERS_KEY)
        sessionStorage.removeItem(REPORT_SEARCH_KEY)
      } catch { /* 无害：读不到就不清 */ }
    }
    window.addEventListener('pagehide', clearListFilters)
    window.addEventListener('beforeunload', clearListFilters)
    return () => {
      window.removeEventListener('pagehide', clearListFilters)
      window.removeEventListener('beforeunload', clearListFilters)
    }
  }, [])

  // 启动时检查登录状态
  useEffect(() => {
    if (location.pathname === '/login') {
      setLoading(false)
      return
    }
    getMe()
      .then((u) => {
        setUser(u)
        if (u.must_change_password) {
          setForcePwd(true)
          setPwdModalOpen(true)
        }
      })
      .catch(() => {
        // 未登录，跳登录页
        setUser(null)
        if (location.pathname !== '/login') navigate('/login')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLogin = (u: UserInfo, mustChange: boolean) => {
    setUser(u)
    if (mustChange) {
      setForcePwd(true)
      setPwdModalOpen(true)
    }
    // 按角色跳转默认页：admin/viewer 去看板，manager/engineer 去项目列表，reporter 去填报页
    const defaultPath = u.role === 'reporter'
      ? '/report'
      : u.role === 'manager' || u.role === 'engineer'
      ? '/projects'
      : '/'
    navigate(defaultPath)
  }

  const handleLogout = async () => {
    try {
      await logout()
    } catch {
      // 忽略
    }
    setUser(null)
    navigate('/login')
  }

  const selectedKey = location.pathname.startsWith('/report')
    ? 'report'
    : location.pathname.startsWith('/resources')
    ? 'resources'
    : location.pathname.startsWith('/admin-center')
    ? 'admin-center'
    : location.pathname.startsWith('/special-projects')
    ? 'special-projects' // 专项列表/详情（含 /special-projects/:id）都高亮「专项项目」——须在 /projects 判定之前
    : location.pathname.startsWith('/projects')
    ? 'projects'
    : location.pathname.startsWith('/users')
    ? 'users'
    : location.pathname.startsWith('/review')
    ? 'review'
    : location.pathname.startsWith('/my-tasks')
    ? 'my-tasks'
    : 'dashboard'

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  // 登录页
  if (!user) {
    if (location.pathname === '/login') {
      return <LoginPage onLogin={handleLogin} />
    }
    return <Navigate to="/login" replace />
  }

  // 导航项（按角色）
  // 导航标签：reporter 仅见「信息填报」（用户 2026-10-29 权限分级需求 1）；
  // viewer 仅见「看板/项目列表」（用户 2026-11-11 权限分级需求 1）；
  // 其余角色显示全部页面标签（页面内权限仍按角色守卫）
  const ALL_NAV_ITEMS = [
    { key: 'dashboard', icon: <DashboardOutlined />, label: '看板' },
    { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
    { key: 'special-projects', icon: <StarOutlined />, label: '专项项目' },
    { key: 'resources', icon: <TeamOutlined />, label: '资源负载' },
    { key: 'admin-center', icon: <AuditOutlined />, label: '审核管理中心' },
    { key: 'report', icon: <FormOutlined />, label: '信息填报' },
  ]
  const navItems = user.role === 'reporter'
    ? ALL_NAV_ITEMS.filter((i) => i.key === 'report')
    : user.role === 'viewer'
    ? ALL_NAV_ITEMS.filter((i) => i.key === 'dashboard' || i.key === 'projects') // 观察者仅见「看板/项目列表」（用户 2026-11-11 权限分级需求 1）
    : ALL_NAV_ITEMS

  // 用户下拉菜单
  const userMenu = {
    items: [
      {
        key: 'changePwd',
        icon: <KeyOutlined />,
        label: '修改密码',
        onClick: () => { setForcePwd(false); setPwdModalOpen(true) },
      },
      { type: 'divider' as const },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: handleLogout,
      },
    ],
  }

  return (
    <ErrorBoundary>
      <Layout style={{ minHeight: '100vh' }}>
        <Header className="pm-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            <div style={{ color: 'var(--text-primary)', fontSize: 17, fontWeight: 600, marginRight: 32, letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="pm-logo-badge"><ProjectOutlined /></span>
              <span className="pm-logo-text">研发项目管理平台</span>
            </div>
            <Menu
              theme={mode === 'dark' ? 'dark' : 'light'}
              mode="horizontal"
              selectedKeys={[selectedKey]}
              onClick={({ key }) => {
                if (key === 'dashboard') navigate('/')
                else if (key === 'projects') navigate('/projects')
                else if (key === 'special-projects') navigate('/special-projects')
                else if (key === 'resources') navigate('/resources')
                else if (key === 'admin-center') navigate('/admin-center')
                else if (key === 'report') navigate('/report')
              }}
              items={navItems}
              style={{ minWidth: 280, background: 'transparent' }}
            />
          </Space>
          <Space size={4}>
            {/* 深色/浅色模式开关 */}
            <Button
              type="text"
              icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggle}
              style={{ color: 'var(--text-primary)', fontSize: 16 }}
              title={mode === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            />
            <NotificationBell />
            <Dropdown menu={userMenu} trigger={['click', 'hover']}>
              <div style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '4px 8px', borderRadius: 6, transition: 'background .2s' }} className="header-user">
                <Avatar size={28} className="pm-avatar" style={{ flexShrink: 0 }}>{user.name.charAt(0)}</Avatar>
                <span>{user.name}</span>
                <DownOutlined style={{ fontSize: 10 }} />
              </div>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Suspense fallback={<Spin size="large" style={{ display: 'block', margin: '100px auto' }} />}>
            <Routes>
              {/* 信息填报（信息填报一期）：admin/manager/engineer/reporter 可达（reporter 主页面；平台角色也可协作填报）；
                  viewer 只读两页不含填报（用户 2026-11-11 权限分级需求 1） */}
              <Route path="/report" element={
                user.role === 'viewer' ? <Navigate to="/" replace /> : <ReportPage user={user} />
              } />
              {/* 看板仅 admin + viewer 可见，manager/engineer 重定向到项目列表；资源负载 admin/manager 可见（效率分析 Tab 仅 admin/manager；viewer 2026-11-11 起只读两页不含资源）；reporter 隔离回填报页（评审 #74） */}
              <Route path="/" element={
                user.role === 'reporter'
                  ? <Navigate to="/report" replace />
                  : user.role === 'manager' || user.role === 'engineer'
                  ? <Navigate to="/projects" replace />
                  : <DashboardPage />
              } />
              {/* reporter 角色隔离（§3.1）：平台页面全部回填报页（各路由独立守卫，不可用通配——
                  react-router 按特异性匹配，通配会被具体路由压过，实测 /projects 穿透） */}
              <Route path="/projects" element={
                user.role === 'reporter' ? <Navigate to="/report" replace /> : <ProjectListPage />
              } />
              <Route path="/projects/:id" element={
                user.role === 'reporter' ? <Navigate to="/report" replace /> : <ProjectDetailPage />
              } />
              {/* 专项项目：仅 admin/manager 可见（与审核中心同模式） */}
              <Route path="/special-projects" element={
                user.role === 'admin' || user.role === 'manager'
                  ? <SpecialProjectsPage />
                  : user.role === 'reporter'
                  ? <Navigate to="/report" replace />
                  : <Navigate to="/" replace />
              } />
              {/* 专项项目详情：复用详情页（is_special 驱动返回按钮），并套用与列表相同的角色守卫——
                  独立路由保证顶部菜单高亮停留在「专项项目」而非「项目列表」 */}
              <Route path="/special-projects/:id" element={
                user.role === 'admin' || user.role === 'manager'
                  ? <ProjectDetailPage />
                  : user.role === 'reporter'
                  ? <Navigate to="/report" replace />
                  : <Navigate to="/" replace />
              } />
               {/* 资源负载（过程审计归组后第 4 Tab 在此）：admin/manager/engineer 可见——
                   engineer 仅见「过程审计」Tab（用户 2026-11-13 功能优化裁定 ①） */}
               <Route path="/resources" element={
                 user.role === 'admin' || user.role === 'manager' || user.role === 'engineer'
                  ? <ResourcePage />
                  : user.role === 'reporter'
                  ? <Navigate to="/report" replace />
                  : <Navigate to="/" replace />
              } />
               {/* 审核管理中心（用户管理+审核中心双板块） */}
               <Route path="/admin-center" element={
                 user.role === 'admin'
                   ? <AdminCenterPage />
                   : user.role === 'reporter'
                     ? <Navigate to="/report" replace />
                     : <Navigate to="/projects" replace />
               } />
               {/* 过程审计已归组进资源负载页第 4 Tab（用户 2026-11-13 功能优化）——旧路径重定向，
                   角色守卫由 /resources 统一接管；API 层维持登录可见（审计透明，reporter 由封锁矩阵挡） */}
               <Route path="/process-audit" element={<Navigate to="/resources" replace />} />
               {/* 旧路径重定向 */}
               <Route path="/users" element={<Navigate to="/admin-center" replace />} />
               <Route path="/review" element={<Navigate to="/admin-center" replace />} />
               <Route path="/team-efficiency" element={<Navigate to="/resources" replace />} />
              {/* 我的任务仅 manager + engineer */}
              <Route path="/my-tasks" element={
                user.role === 'manager' || user.role === 'engineer'
                  ? <MyTasksPage />
                  : user.role === 'reporter'
                  ? <Navigate to="/report" replace />
                  : <Navigate to="/" replace />
              } />
              <Route path="/login" element={user.role === 'reporter' ? <Navigate to="/report" replace /> : <Navigate to="/" replace />} />
              {/* 兜底：reporter 回填报页，其余回首页（置于末尾，仅无其他匹配时生效） */}
              <Route path="*" element={
                user.role === 'reporter' ? <Navigate to="/report" replace /> : <Navigate to="/" replace />
              } />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
      <ChangePasswordModal
        open={pwdModalOpen}
        forceChange={forcePwd}
        onCancel={() => setPwdModalOpen(false)}
        onSuccess={() => {
          setPwdModalOpen(false)
          setForcePwd(false)
          setUser({ ...user, must_change_password: false })
        }}
      />
    </ErrorBoundary>
  )
}
