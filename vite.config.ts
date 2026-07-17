import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': {
          target: env.VITE_BACKEND_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
