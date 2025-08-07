import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './', // 确保打包后的路径是相对路径
  server: {
    host: '0.0.0.0', // 监听所有接口
    port: 5173,
    hmr: false, // 禁用热模块更新，以兼容强制门户的迷你浏览器
  },
})
