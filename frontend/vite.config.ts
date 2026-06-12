/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import vueI18n from '@intlify/unplugin-vue-i18n/vite'
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
    // Relative asset base so the built SPA is portable to ANY mount point — served at
    // the panel's own origin root (:8090) OR proxied under a subpath (e.g. /filamind/ on
    // the printer's Mainsail nginx, which a Cloudflare tunnel already exposes). With
    // relative assets + hash routing, the same dist works at every mount with no rebuild.
    base: './',
    plugins: [
      vue(),
      // Precompiles the locale JSON in src/locales/** and wires vue-i18n's feature flags.
      // runtimeOnly stays off for now so the message compiler is available for the catalogs
      // loaded dynamically via import.meta.glob; a later phase can enable it once precompilation
      // of every catalog is verified, to drop the compiler from the bundle.
      vueI18n({
        include: [fileURLToPath(new URL('./src/locales/**', import.meta.url))],
        runtimeOnly: false,
        compositionOnly: true,
        strictMessage: false,
        escapeHtml: false,
      }),
    ],
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
