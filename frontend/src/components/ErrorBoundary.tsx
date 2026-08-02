import { Component, type ReactNode } from 'react'

interface State {
  hasError: boolean
  error?: Error
}

// 全局错误边界：捕获子组件渲染/模块加载错误，避免整页白屏
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: any) {
    console.error('ErrorBoundary 捕获:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40 }}>
          <h2>页面渲染出错</h2>
          <pre style={{ background: '#f5f5f5', padding: 16, overflow: 'auto' }}>
            {this.state.error?.message}
            {'\n\n'}
            {this.state.error?.stack}
          </pre>
          <button onClick={() => location.reload()} style={{ marginTop: 16, padding: '6px 16px' }}>
            重新加载
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
