/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const moonraker = env.VITE_MOONRAKER_HTTP_URL || 'http://localhost:7125'
  const backend = env.VITE_BACKEND_URL || 'http://localhost:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // Dev-only reverse proxy so the SPA can reach Moonraker + the backend
      // without CORS during local development.
      proxy: {
        '/server': { target: moonraker, changeOrigin: true },
        '/printer': { target: moonraker, changeOrigin: true },
        '/access': { target: moonraker, changeOrigin: true },
        '/machine': { target: moonraker, changeOrigin: true },
        '/websocket': { target: moonraker, ws: true, changeOrigin: true },
        '/api': { target: backend, changeOrigin: true },
      },
    },
    build: {
      target: 'es2020',
      sourcemap: false,
    },
    test: {
      environment: 'jsdom',
    },
  }
})
