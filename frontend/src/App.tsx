import { lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Spin } from 'antd'
import { DashboardOutlined, ProjectOutlined, TeamOutlined } from '@ant-design/icons'
import DashboardPage from './pages/DashboardPage'

// 懒加载详情页和资源页（含 GanttChart/dhtmlx-gantt），避免影响首页初始加载
const ProjectListPage = lazy(() => import('./pages/ProjectListPage'))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))
const ResourcePage = lazy(() => import('./pages/ResourcePage'))

const { Header, Content } = Layout

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()

  // 根据当前路径高亮导航项
  const selectedKey = location.pathname.startsWith('/resources')
    ? 'resources'
    : location.pathname.startsWith('/projects')
    ? 'projects'
    : 'dashboard'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginRight: 32 }}>
          🦞 研发项目管理平台
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => {
            if (key === 'dashboard') navigate('/')
            if (key === 'projects') navigate('/projects')
            if (key === 'resources') navigate('/resources')
          }}
          items={[
            { key: 'dashboard', icon: <DashboardOutlined />, label: '看板' },
            { key: 'projects', icon: <ProjectOutlined />, label: '项目列表' },
            { key: 'resources', icon: <TeamOutlined />, label: '资源负载' },
          ]}
          style={{ minWidth: 280 }}
        />
      </Header>
      <Content style={{ padding: 24 }}>
        <Suspense fallback={<Spin size="large" style={{ display: 'block', margin: '100px auto' }} />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/projects" element={<ProjectListPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/resources" element={<ResourcePage />} />
          </Routes>
        </Suspense>
      </Content>
    </Layout>
  )
}
