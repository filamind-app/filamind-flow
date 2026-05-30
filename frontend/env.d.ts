/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Moonraker REST base URL (no trailing slash). Falls back to the current host:7125. */
  readonly VITE_MOONRAKER_HTTP_URL?: string
  /** Moonraker WebSocket URL. Falls back to ws(s)://<host>:7125/websocket. */
  readonly VITE_MOONRAKER_WS_URL?: string
  /** FilaMind Flow backend base URL. Falls back to the current host:8000. */
  readonly VITE_BACKEND_URL?: string
  /** Optional UI title override. */
  readonly VITE_APP_TITLE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
