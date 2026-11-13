import { useEffect, useRef, useState } from 'react'
import { Form, message } from 'antd'
import { ArrowRightOutlined, EyeInvisibleOutlined, EyeOutlined, LoadingOutlined } from '@ant-design/icons'
import { login } from '../api/auth'
import LoginStarfield from '../components/LoginStarfield'
import type { UserInfo } from '../types'

interface Props {
  onLogin: (user: UserInfo, mustChangePassword: boolean) => void
}

interface Ripple {
  id: number
  x: number
  y: number
  size: number
}

/* 壁纸资产（构建期生成，见 scripts/gen_wallpapers.py）：登录页恒深色（2026-11-13 用户裁定），
   只挂深色版；WebP 优先 + 同宽 JPEG 兜底，5504 原图作最高档。srcset 按视口宽选档，
   devicePixelRatio 2 自动上一档。浅色版资产保留在库备用、不上引用。 */
const WALLPAPER_SETS = {
  dark: {
    webp:
      '/wallpapers/wallpaper-dark-1920.webp 1920w, ' +
      '/wallpapers/wallpaper-dark-2560.webp 2560w, ' +
      '/wallpapers/wallpaper-dark-3840.webp 3840w',
    jpg:
      '/wallpapers/wallpaper-dark-1920.jpg 1920w, ' +
      '/wallpapers/wallpaper-dark-2560.jpg 2560w, ' +
      '/wallpapers/wallpaper-dark-3840.jpg 3840w, ' +
      '/wallpapers/wallpaper-dark-5504.jpg 5504w',
    fallback: '/wallpapers/wallpaper-dark-5504.jpg',
  },
} as const

/* 平玻璃态输入（照片背景上的变体）：受控值兜底为空串，避免 Form.Item 注入值 undefined→串的受控切换告警。
   摇头校验（用户裁定）：空输入/登录失败时加 login-field--shake 类，animationend 后由组件清状态；
   不用 antd rules——校验错误不再显示输入框下方红字。 */
function NeuInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { value, className, ...rest } = props
  return <input {...rest} value={value ?? ''} className={['login-field', className].filter(Boolean).join(' ')} />
}

export default function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false)
  const [showPwd, setShowPwd] = useState(false)
  const [shakeUser, setShakeUser] = useState(false)
  const [shakePwd, setShakePwd] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [arrowSlide, setArrowSlide] = useState(false)
  const [ripples, setRipples] = useState<Ripple[]>([])
  const rippleSeq = useRef(0)
  const rippleTimers = useRef<number[]>([])
  const errorTimer = useRef<number>(0)
  useEffect(
    () => () => {
      rippleTimers.current.forEach((t) => window.clearTimeout(t))
      window.clearTimeout(errorTimer.current)
    },
    [],
  ) // 卸载清全部待清定时器

  /* 按钮涟漪：点击处生成圆形扩散波纹（参考 CSDN 星空登录页教程的 ripple 做法） */
  const spawnRipple = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const id = ++rippleSeq.current
    setRipples((rs) => [
      ...rs,
      {
        id,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        size: Math.max(rect.width, rect.height) * 2.2,
      },
    ])
    const timer = window.setTimeout(() => setRipples((rs) => rs.filter((r) => r.id !== id)), 650)
    rippleTimers.current.push(timer)
  }

  /* 登录失败错误浮字：渐现渐隐（0.35s 过渡、3.5s 自动消散），不弹顶部消息（用户裁定） */
  const showError = (text: string) => {
    window.clearTimeout(errorTimer.current)
    setLoginError(text)
    errorTimer.current = window.setTimeout(() => setLoginError(null), 3500)
    rippleTimers.current.push(errorTimer.current)
  }

  /* 摇头结束清状态（按 animationName 过滤——涟漪的 animationend 也会冒泡到不了这里，input 只 shake） */
  const shakeEnd = (which: 'u' | 'p') => (e: React.AnimationEvent<HTMLInputElement>) => {
    if (e.animationName !== 'neu-shake') return
    if (which === 'u') setShakeUser(false)
    else setShakePwd(false)
  }

  const handleSubmit = async (values: { username: string; password: string }) => {
    const missingUser = !values.username?.trim()
    const missingPwd = !values.password?.trim()
    if (missingUser || missingPwd) {
      /* 空输入：只摇头示意需要输入，不显示红字（用户裁定，macOS 同款） */
      if (missingUser) setShakeUser(true)
      if (missingPwd) setShakePwd(true)
      return
    }
    setLoading(true)
    try {
      const result = await login(values.username, values.password)
      message.success(`欢迎，${result.user.name}`)
      onLogin(result.user, result.must_change_password)
    } catch (e) {
      /* 登录失败：密码框摇头 + 错误浮字（不弹顶部，用户裁定） */
      setShakePwd(true)
      showError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    /* 登录页恒深色：data-mode 固定 dark，不随 html[data-theme]（换肤只在进入平台后，2026-11-13 用户裁定） */
    <div className="pm-login" data-mode="dark">
      {/* 深色壁纸层（单版恒深色）+ Ken Burns 缩放（恒动，2026-11-13 裁定豁免降级） */}
      <div className="neu-wall" aria-hidden="true">
        <div className="neu-wall__layer neu-wall__layer--dark">
          <picture>
            <source type="image/webp" srcSet={WALLPAPER_SETS.dark.webp} sizes="100vw" />
            <img src={WALLPAPER_SETS.dark.fallback} srcSet={WALLPAPER_SETS.dark.jpg} sizes="100vw" alt="" />
          </picture>
        </div>
        <div className="neu-wall__scrim" />
      </div>

      {/* 动态星空层（Canvas 恒动闪烁）——叠在真实壁纸之上 */}
      <LoginStarfield />

      {/* 顶部居中：毛玻璃字面标题·清晰版（无弥散光晕、无时间与日期）——用户 2026-11-13 裁定 */}
      <div className="neu-login__top">
        <h1 className="neu-glass-title glass-text">项目管理中心</h1>
      </div>

      {/* 无登录卡：登录行直接浮于壁纸、靠底部一行横排三件
          （用户名 → 密码带显隐眼 → 圆形箭头登录钮）；主题切换钮已移除——换肤只在平台内（用户裁定） */}
      <div className="neu-login__stage">
        <Form onFinish={handleSubmit} className="neu-login__row">
          <Form.Item name="username">
            <NeuInput
              placeholder="用户名"
              autoComplete="username"
              aria-label="用户名"
              className={shakeUser ? 'login-field--shake' : undefined}
              onAnimationEnd={shakeEnd('u')}
            />
          </Form.Item>
          <div className="login-field-wrap">
            <Form.Item name="password">
              <NeuInput
                placeholder="密码"
                autoComplete="current-password"
                aria-label="密码"
                type={showPwd ? 'text' : 'password'}
                className={shakePwd ? 'login-field--shake' : undefined}
                onAnimationEnd={shakeEnd('p')}
              />
            </Form.Item>
            {/* 密码显隐（同教程做法：输入框右侧切换明文/密文） */}
            <button
              type="button"
              className="login-pwd-toggle"
              onClick={() => setShowPwd((v) => !v)}
              aria-label={showPwd ? '隐藏密码' : '显示密码'}
            >
              {showPwd ? <EyeOutlined /> : <EyeInvisibleOutlined />}
            </button>
          </div>
          <div className="login-btn-wrap">
            <button
              className={`neu-icon-btn${arrowSlide ? ' login-btn--slide' : ''}`}
              type="submit"
              disabled={loading}
              onClick={(e) => {
                spawnRipple(e)
                if (!loading) setArrowSlide(true)
              }}
              onAnimationEnd={(e) => {
                if (e.animationName === 'neu-arrow-in') setArrowSlide(false)
              }}
              aria-label="登录"
            >
              {loading ? <LoadingOutlined /> : <ArrowRightOutlined />}
              {ripples.map((r) => (
                <span
                  key={r.id}
                  className="neu-ripple"
                  style={{ left: r.x - r.size / 2, top: r.y - r.size / 2, width: r.size, height: r.size }}
                />
              ))}
            </button>
            {/* 登录失败错误浮字：按钮右侧渐现渐隐（不弹顶部，用户裁定） */}
            <span className={`login-error-float${loginError ? ' login-error-float--show' : ''}`} role="alert">
              {loginError}
            </span>
          </div>
        </Form>
      </div>

      <div className="neu-login__footer">© 2026 研发项目管理平台</div>
    </div>
  )
}
