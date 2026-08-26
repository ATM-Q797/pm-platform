import { useEffect, useState, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import { Layout, Menu, Spin, Dropdown, Space, Tag, Avatar, Button } from 'antd'
import {
  DashboardOutlined,
  ProjectOutlined,
  TeamOutlined,
  UserOutlined,
  LogoutOutlined,
  KeyOutlined,
  DownOutlined,
  AuditOutlined,
  CheckSquareOutlined,
  FileTextOutlined,
  MoonOutlined,
  SunOutlined,
} from '@ant-design/icons'
import ErrorBoundary from './components/ErrorBoundary'
import LoginPage from './pages/LoginPage'
import ChangePasswordModal from './components/ChangePasswordModal'
import DashboardPage from './pages/DashboardPage'
import { getMe, logout } from './api/auth'
import { useTheme } from './theme'
import type { UserInfo } from './types'

// 懒加载详情页和资源页（含 GanttChart/dhtmlx-gantt），避免影响首页初始加载
const ProjectListPage = lazy(() => import('./pages/ProjectListPage'))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))
const UserManagePage = lazy(() => import('./pages/UserManagePage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const MyTasksPage = lazy(() => import('./pages/MyTasksPage'))
const ReportPage = lazy(() => import('./pages/ReportPage'))

const { Header, Content } = Layout

// 角色显示名 + Tag 颜色
const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  manager: '项目负责人',
  engineer: '工程师',
  viewer: '观察者',
}
const ROLE_COLOR: Record<string, string> = {
  admin: 'red',
  manager: 'blue',
  engineer: 'green',
  viewer: 'default',
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const { mode, toggle } = useTheme() // 深色/浅色模式
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [forcePwd, setForcePwd] = useState(false)

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
    // 按角色跳转默认页：admin/viewer 去看板，manager/engineer 去项目列表
    const defaultPath = u.role === 'manager' || u.role === 'engineer' ? '/projects' : '/'
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

  const selectedKey = location.pathname.startsWith('/resources')
    ? 'resources'
    : location.pathname.startsWith('/projects')
    ? 'projects'
    : location.pathname.startsWith('/users')
    ? 'users'
    : location.pathname.startsWith('/review')
    ? 'review'
    : location.pathname.startsWith('/my-tasks')
    ? 'my-tasks'
    : location.pathname.startsWith('/reports')
    ? 'reports'
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
  // - admin：全部（看板/项目/资源/用户管理/审核中心）
  // - manager：项目列表 + 我的任务（不需要看板和资源负载）
  // - engineer：项目列表 + 我的任务（不需要看板和资源负载）
  // - viewer：看板/项目列表/资源负载（只读）
  const navItems =
    user.role === 'admin'
      ? [
          { key: 'dashboard', icon: <DashboardOutlined />, label: '看板' },
          { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
          { key: 'resources', icon: <TeamOutlined />, label: '资源负载' },
          { key: 'reports', icon: <FileTextOutlined />, label: '周报' },
          { key: 'users', icon: <UserOutlined />, label: '用户管理' },
          { key: 'review', icon: <AuditOutlined />, label: '审核中心' },
        ]
      : user.role === 'manager' || user.role === 'engineer'
      ? [
          { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
          { key: 'my-tasks', icon: <CheckSquareOutlined />, label: '我的任务' },
          ...(user.role === 'manager'
            ? [
                { key: 'reports', icon: <FileTextOutlined />, label: '周报' },
                { key: 'review', icon: <AuditOutlined />, label: '审核中心' },
              ]
            : []),
        ]
      : // viewer
        [
          { key: 'dashboard', icon: <DashboardOutlined />, label: '看板' },
          { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
          { key: 'resources', icon: <TeamOutlined />, label: '资源负载' },
        ]

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
                else if (key === 'resources') navigate('/resources')
                else if (key === 'users') navigate('/users')
                else if (key === 'review') navigate('/review')
                else if (key === 'my-tasks') navigate('/my-tasks')
                else if (key === 'reports') navigate('/reports')
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
            <Dropdown menu={userMenu} trigger={['click', 'hover']}>
              <div style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '4px 8px', borderRadius: 6, transition: 'background .2s' }} className="header-user">
                <Avatar size={28} className="pm-avatar" style={{ flexShrink: 0 }}>{user.name.charAt(0)}</Avatar>
                <span>{user.name}</span>
                <Tag color={ROLE_COLOR[user.role] || 'default'} style={{ margin: 0 }}>{ROLE_LABEL[user.role]}</Tag>
                <DownOutlined style={{ fontSize: 10 }} />
              </div>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Suspense fallback={<Spin size="large" style={{ display: 'block', margin: '100px auto' }} />}>
            <Routes>
              {/* 看板/资源负载仅 admin + viewer 可见，manager/engineer 重定向到项目列表 */}
              <Route path="/" element={
                user.role === 'manager' || user.role === 'engineer'
                  ? <Navigate to="/projects" replace />
                  : <DashboardPage />
              } />
              <Route path="/projects" element={<ProjectListPage />} />
              <Route path="/projects/:id" element={<ProjectDetailPage />} />
              <Route path="/resources" element={
                user.role === 'manager' || user.role === 'engineer'
                  ? <Navigate to="/projects" replace />
                  : <ResourcePage />
              } />
              {/* 用户管理/审核中心仅 admin */}
              <Route path="/users" element={
                user.role === 'admin' ? <UserManagePage /> : <Navigate to="/" replace />
              } />
              <Route path="/review" element={
                user.role === 'admin' || user.role === 'manager'
                  ? <ReviewPage userRole={user.role} />
                  : <Navigate to="/" replace />
              } />
              {/* 我的任务仅 manager + engineer */}
              <Route path="/my-tasks" element={
                user.role === 'manager' || user.role === 'engineer'
                  ? <MyTasksPage />
                  : <Navigate to="/" replace />
              } />
              {/* 周报仅 admin + manager */}
              <Route path="/reports" element={
                user.role === 'admin' || user.role === 'manager'
                  ? <ReportPage />
                  : <Navigate to="/" replace />
              } />
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
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
