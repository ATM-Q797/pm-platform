import { useState } from 'react'
import { Form, Input, Button, message, Typography } from 'antd'
import { UserOutlined, LockOutlined, ProjectOutlined } from '@ant-design/icons'
import { login } from '../api/auth'
import { useTheme } from '../theme'
import LoginGridCanvas from '../components/LoginGridCanvas'
import type { UserInfo } from '../types'

interface Props {
  onLogin: (user: UserInfo, mustChangePassword: boolean) => void
}

export default function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false)
  const { mode } = useTheme()
  const isDark = mode === 'dark'

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const result = await login(values.username, values.password)
      message.success(`欢迎，${result.user.name}`)
      onLogin(result.user, result.must_change_password)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="pm-login"
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: isDark
          ? 'radial-gradient(1200px 600px at 50% -10%, #1a2332 0%, #0f1115 60%)'
          : 'radial-gradient(1200px 600px at 50% -10%, #eaf2ff 0%, #f5f7fa 55%)',
      }}
    >
      {/* 动态网格背景层：波浪涌动 + 指针扰动（reduced-motion 下静态一帧） */}
      <LoginGridCanvas />

      {/* 顶部极简 logo 行（DeepSeek 式） */}
      <div style={{ padding: '24px 32px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <ProjectOutlined style={{ fontSize: 22, color: 'var(--accent-cyan)' }} />
        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
          研发项目管理平台
        </span>
      </div>

      {/* 中央区：大标题 + 副标题 + 登录卡片 */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 24px 64px',
          gap: 48,
        }}
      >
        <div style={{ textAlign: 'center', maxWidth: 640 }}>
          <Typography.Title
            style={{
              fontSize: 40,
              fontWeight: 700,
              margin: 0,
              letterSpacing: 1,
              color: 'var(--text-primary)',
            }}
          >
            项目管理中心
          </Typography.Title>
          <Typography.Text
            style={{ fontSize: 16, color: 'var(--text-secondary)', marginTop: 12, display: 'block' }}
          >
            让每一个项目进度清晰可见
          </Typography.Text>
        </div>

        {/* 登录卡片：大圆角、无边框、阴影悬浮、半透明底 */}
        <div
          style={{
            width: 380,
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(8px)',
            border: 'none',
            borderRadius: 16,
            padding: '32px 28px',
            boxShadow: 'var(--card-shadow)',
          }}
        >
          <Form onFinish={handleSubmit} size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input
                prefix={<UserOutlined style={{ color: 'var(--text-tertiary)' }} />}
                placeholder="用户名"
                autoComplete="username"
                style={{ borderRadius: 10 }}
              />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--text-tertiary)' }} />}
                placeholder="密码"
                autoComplete="current-password"
                style={{ borderRadius: 10 }}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                style={{ borderRadius: 10, height: 44, fontWeight: 600 }}
              >
                登录
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>

      {/* 底部 */}
      <div style={{ padding: '16px 0', textAlign: 'center', fontSize: 12, color: 'var(--text-tertiary)' }}>
        © 2026 研发项目管理平台
      </div>
    </div>
  )
}
