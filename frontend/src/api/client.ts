import axios from 'axios'

// 通过 vite proxy 转发到后端 8000，前端用相对路径 /api 即可
const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true, // 认证：自动携带 httpOnly Cookie
})

// 响应拦截：401 跳登录，其他错误统一提示
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && !location.pathname.startsWith('/login')) {
      // 未登录或登录过期，跳转登录页
      location.href = '/login'
      return Promise.reject(new Error('请先登录'))
    }
    // detail 可能是字符串 / 数组（422 校验）/ 对象——统一序列化，避免 message 变 "[object Object]"
    const raw = error.response?.data?.detail ?? error.message ?? '请求失败'
    const msg = typeof raw === 'string' ? raw : JSON.stringify(raw)
    return Promise.reject(new Error(msg))
  }
)

export default client
