import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
    watch:
      process.env.CHOKIDAR_USEPOLLING === 'true'
        ? { usePolling: true }
        : undefined,
  },
})
