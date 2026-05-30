/** Resolved Moonraker + backend endpoints. */
export interface Endpoints {
  httpUrl: string
  wsUrl: string
  backendUrl: string
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

/**
 * Resolves endpoints from build-time env, defaulting to the **same origin**.
 *
 * The panel is served behind a proxy that forwards Moonraker + backend traffic —
 * nginx in production, the Vite dev server in development — so by default there is
 * no CORS and no host/port baked into the build. Override with VITE_MOONRAKER_*
 * only to talk to a different origin directly.
 */
export function resolveEndpoints(): Endpoints {
  const { origin, protocol, host } = window.location
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'

  const httpUrl = stripTrailingSlash(import.meta.env.VITE_MOONRAKER_HTTP_URL || origin)
  const wsUrl = import.meta.env.VITE_MOONRAKER_WS_URL || `${wsProtocol}//${host}/websocket`
  const backendUrl = stripTrailingSlash(import.meta.env.VITE_BACKEND_URL || origin)

  return { httpUrl, wsUrl, backendUrl }
}
