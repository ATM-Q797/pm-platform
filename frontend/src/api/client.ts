import axios from 'axios'

// 通过 vite proxy 转发到后端 8000，前端用相对路径 /api 即可
const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 响应拦截：统一错误提示（调用方可捕获）
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export default client
