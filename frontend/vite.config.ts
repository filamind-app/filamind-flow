/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import vueI18n from '@intlify/unplugin-vue-i18n/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

// The app's own version, read from package.json at build time and injected as a compile-time
// constant (see __APP_VERSION__ in env.d.ts). Used in the in-app feedback/bug-report diagnostics
// so a report names the exact build it came from.
const pkgVersion = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'),
).version as string

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
    // Relative asset base so the built SPA is portable to ANY mount point - served at
    // the panel's own origin root (:8090) OR proxied under a subpath (e.g. /filamind/ on
    // the printer's Mainsail nginx, which a Cloudflare tunnel already exposes). With
    // relative assets + hash routing, the same dist works at every mount with no rebuild.
    base: './',
    define: {
      __APP_VERSION__: JSON.stringify(pkgVersion),
    },
    plugins: [
      vue(),
      // Precompiles the locale JSON in src/locales/** and wires vue-i18n's feature flags.
      // Every catalog (including the lazy-loaded ones) lives under the include glob, so they are
      // all precompiled at build time. runtimeOnly then drops the message compiler from the bundle.
      vueI18n({
        include: [fileURLToPath(new URL('./src/locales/**', import.meta.url))],
        runtimeOnly: true,
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
      rollupOptions: {
        // Two entries: the Neo-Brutalist web UI (index.html) + the native touch app (touch.html,
        // served at :8090/touch.html and loaded by the Tauri kiosk). Each is its own bundle.
        //
        // NOTE: no hand-rolled `manualChunks`. Force-merging vue/pinia/vue-i18n into a single
        // 'vendor' chunk ACROSS two entries orphaned a Rollup ESM-interop helper, crashing BOTH
        // entries on load with "e is not a function" (the web panel went blank after the touch
        // entry landed). Letting Rollup split per-entry keeps each chunk's injected helpers intact.
        // A shared long-lived vendor chunk is a cache-locality nicety, not worth a correctness risk
        // on this infrequently-updated panel.
        input: {
          main: fileURLToPath(new URL('./index.html', import.meta.url)),
          touch: fileURLToPath(new URL('./touch.html', import.meta.url)),
        },
      },
    },
    test: {
      environment: 'jsdom',
    },
  }
})
