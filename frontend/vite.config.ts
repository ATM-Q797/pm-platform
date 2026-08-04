import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // 把 /api 请求代理到后端 FastAPI，前端代码用相对路径 /api 即可
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    // 生产构建优化
    build: {
      // 产物输出到 dist/
      outDir: 'dist',
      // 拆分代码块，避免单个 JS 文件过大
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-router')) return 'vendor-react'
              if (id.includes('antd') || id.includes('@ant-design')) return 'vendor-antd'
              if (id.includes('dhtmlx-gantt')) return 'vendor-gantt'
            }
          },
        },
      },
      // 提高 chunk 大小警告阈值
      chunkSizeWarningLimit: 1000,
    },
  }
})
