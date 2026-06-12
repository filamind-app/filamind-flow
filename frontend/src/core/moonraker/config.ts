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
 * The path prefix the SPA is mounted under, derived from the document's own location so the
 * same build works at the origin root (`:8090/` → ``) and under a reverse-proxy subpath
 * (`…/filamind/` → `/filamind`). Hash routing keeps `pathname` pinned to the mount point, so
 * the directory of the current document IS the mount prefix. Every same-origin call
 * (`/api`, `/server`, `/websocket`) is then issued relative to it, so a subpath proxy that
 * strips the prefix lands on the panel's own nginx unchanged.
 */
export function mountPrefix(): string {
  const dir = window.location.pathname.replace(/\/[^/]*$/, '')
  return dir === '/' ? '' : dir
}

/**
 * Resolves endpoints, defaulting to the **same origin + mount prefix**.
 *
 * The panel is served behind a proxy that forwards Moonraker + backend traffic — nginx in
 * production, the Vite dev server in development — so by default there is no CORS and no
 * host/port baked into the build. It also works when mounted under a subpath (the prefix is
 * derived at runtime). Override with VITE_MOONRAKER_* / VITE_BACKEND_URL to talk to a
 * different origin directly.
 */
export function resolveEndpoints(): Endpoints {
  const { origin, protocol, host } = window.location
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
  const prefix = mountPrefix()

  const httpUrl = stripTrailingSlash(import.meta.env.VITE_MOONRAKER_HTTP_URL || origin + prefix)
  const wsUrl = import.meta.env.VITE_MOONRAKER_WS_URL || `${wsProtocol}//${host}${prefix}/websocket`
  const backendUrl = stripTrailingSlash(import.meta.env.VITE_BACKEND_URL || origin + prefix)

  return { httpUrl, wsUrl, backendUrl }
}
