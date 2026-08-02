import { lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Spin } from 'antd'
import { ProjectOutlined } from '@ant-design/icons'
import ProjectListPage from './pages/ProjectListPage'

// 懒加载详情页（含 GanttChart/dhtmlx-gantt），避免影响列表页初始加载
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))

const { Header, Content } = Layout

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedKey = location.pathname === '/' ? 'projects' : ''

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
          onClick={({ key }) => key === 'projects' && navigate('/')}
          items={[{ key: 'projects', icon: <ProjectOutlined />, label: '项目列表' }]}
          style={{ minWidth: 120 }}
        />
      </Header>
      <Content style={{ padding: 24 }}>
        <Suspense fallback={<Spin size="large" style={{ display: 'block', margin: '100px auto' }} />}>
          <Routes>
            <Route path="/" element={<ProjectListPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
          </Routes>
        </Suspense>
      </Content>
    </Layout>
  )
}
