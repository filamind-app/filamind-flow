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
 * Resolves endpoints from build-time env, falling back to the current host.
 *
 * In production the panel is typically served behind the same host as Moonraker,
 * so the defaults (host:7125 for Moonraker, host:8000 for the backend) usually
 * work without any configuration.
 */
export function resolveEndpoints(): Endpoints {
  const { protocol, hostname } = window.location
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'

  const httpUrl = stripTrailingSlash(
    import.meta.env.VITE_MOONRAKER_HTTP_URL || `${protocol}//${hostname}:7125`,
  )
  const wsUrl = import.meta.env.VITE_MOONRAKER_WS_URL || `${wsProtocol}//${hostname}:7125/websocket`
  const backendUrl = stripTrailingSlash(
    import.meta.env.VITE_BACKEND_URL || `${protocol}//${hostname}:8000`,
  )

  return { httpUrl, wsUrl, backendUrl }
}
