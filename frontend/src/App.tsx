import { useEffect, useState, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import { Layout, Menu, Spin, Dropdown, Button, Space, Tag } from 'antd'
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
} from '@ant-design/icons'
import ErrorBoundary from './components/ErrorBoundary'
import LoginPage from './pages/LoginPage'
import ChangePasswordModal from './components/ChangePasswordModal'
import DashboardPage from './pages/DashboardPage'
import { getMe, logout } from './api/auth'
import type { UserInfo } from './types'

// 懒加载详情页和资源页（含 GanttChart/dhtmlx-gantt），避免影响首页初始加载
const ProjectListPage = lazy(() => import('./pages/ProjectListPage'))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))
const UserManagePage = lazy(() => import('./pages/UserManagePage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const MyTasksPage = lazy(() => import('./pages/MyTasksPage'))

const { Header, Content } = Layout

// 角色显示名
const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  manager: '项目负责人',
  engineer: '工程师',
  viewer: '观察者',
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
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
    navigate('/')
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
  const navItems = [
    { key: 'dashboard', icon: <DashboardOutlined />, label: '看板' },
    { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
    { key: 'resources', icon: <TeamOutlined />, label: '资源负载' },
    ...(user.role === 'admin'
      ? [
          { key: 'users', icon: <UserOutlined />, label: '用户管理' },
          { key: 'review', icon: <AuditOutlined />, label: '审核中心' },
        ]
      : []),
    ...(user.role === 'engineer' || user.role === 'manager'
      ? [{ key: 'my-tasks', icon: <CheckSquareOutlined />, label: '我的任务' }]
      : []),
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
        <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            <div style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginRight: 32 }}>
              🦞 研发项目管理平台
            </div>
            <Menu
              theme="dark"
              mode="horizontal"
              selectedKeys={[selectedKey]}
              onClick={({ key }) => {
                if (key === 'dashboard') navigate('/')
                else if (key === 'projects') navigate('/projects')
                else if (key === 'resources') navigate('/resources')
                else if (key === 'users') navigate('/users')
                else if (key === 'review') navigate('/review')
                else if (key === 'my-tasks') navigate('/my-tasks')
              }}
              items={navItems}
              style={{ minWidth: 280, background: 'transparent' }}
            />
          </Space>
          <Dropdown menu={userMenu}>
            <Button type="text" style={{ color: '#fff' }}>
              <Space>
                <UserOutlined />
                <span>{user.name}</span>
                <Tag color="blue" style={{ margin: 0 }}>{ROLE_LABEL[user.role]}</Tag>
                <DownOutlined />
              </Space>
            </Button>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24 }}>
          <Suspense fallback={<Spin size="large" style={{ display: 'block', margin: '100px auto' }} />}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/projects" element={<ProjectListPage />} />
              <Route path="/projects/:id" element={<ProjectDetailPage />} />
              <Route path="/resources" element={<ResourcePage />} />
              <Route path="/users" element={<UserManagePage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/my-tasks" element={<MyTasksPage />} />
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
