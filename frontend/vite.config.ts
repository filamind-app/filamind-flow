/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Where the dev proxy forwards Moonraker traffic. Set MOONRAKER_PROXY_TARGET to
  // a remote printer to develop against real hardware without touching its config.
  const moonrakerTarget =
    env.MOONRAKER_PROXY_TARGET || env.VITE_MOONRAKER_HTTP_URL || 'http://localhost:7125'
  const backend = env.VITE_BACKEND_URL || 'http://localhost:8000'

  // Strip the browser Origin so Moonraker treats the proxied request as a trusted
  // non-browser client (its cors_domains may not include the dev origin).
  const moonraker = (ws = false): ProxyOptions => ({
    target: moonrakerTarget,
    changeOrigin: true,
    ws,
    configure: (proxy) => {
      proxy.on('proxyReq', (proxyReq) => proxyReq.removeHeader('origin'))
      proxy.on('proxyReqWs', (proxyReq) => proxyReq.removeHeader('origin'))
    },
  })

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/server': moonraker(),
        '/printer': moonraker(),
        '/access': moonraker(),
        '/machine': moonraker(),
        '/websocket': moonraker(true),
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
