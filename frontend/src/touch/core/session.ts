// The single MoonrakerClient + FilaMindSession for the flow touch app, from @filamind-app/core.
// Identity 'display' (an on-printer screen) with a distinct client_name so the host tells it apart
// from the FilaMind screen surface.
import { MoonrakerClient, FilaMindSession, FULL_CONTROL } from '@filamind-app/core'

function defaultWsUrl(): string {
  const env = import.meta.env.VITE_MOONRAKER_WS_URL
  if (env) return env
  const host = typeof window !== 'undefined' ? window.location?.host : ''
  // In the Tauri bundle the webview origin is tauri.localhost - NOT the printer. The touch panel
  // runs on the printer, so default to the local Moonraker. A browser served by Moonraker (or
  // VITE_MOONRAKER_WS_URL) overrides this.
  if (!host || host.includes('tauri') || host.includes('localhost')) {
    return 'ws://localhost:7125/websocket'
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${host}/websocket`
}

const appVersion = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.0.0'

export const connector = new MoonrakerClient({ url: defaultWsUrl() })

export const session = new FilaMindSession(connector, {
  subscriptions: FULL_CONTROL,
  identify: { client_name: 'FilaMind Flow touch', version: appVersion, type: 'display' },
})
