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
  /** URL of the Mainsail UI for the "back" button. Falls back to the host root. */
  readonly VITE_MAINSAIL_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** The app version, injected from package.json at build time (see vite.config.ts `define`). */
declare const __APP_VERSION__: string

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
