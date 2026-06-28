// Single-source DUAL-HOST adapter. One build runs either:
//   - 'mainsail' (default): the current Mainsail-integrated sidebar deployment, or
//   - 'suite':   hosted inside the FilaMind suite,
// selected by the VITE_HOST_MODE build flag. There are no long-lived branches - host-specific
// behaviour funnels through this module so the rest of the app stays host-agnostic.
//
// Policy: new flow innovations are SUITE-exclusive (the Mainsail build stays feature-frozen);
// the few cross-host essentials (e.g. Setup) ship in BOTH. Connection URLs are NOT decided here -
// moonraker/config.ts already resolves them from the origin + VITE_MOONRAKER_* overrides, which
// works for both hosts.

export type HostMode = 'mainsail' | 'suite'

export function hostMode(): HostMode {
  return import.meta.env.VITE_HOST_MODE === 'suite' ? 'suite' : 'mainsail'
}

export function isSuiteHost(): boolean {
  return hostMode() === 'suite'
}

export function isMainsailHost(): boolean {
  return hostMode() === 'mainsail'
}

/** The "back to the host UI" link only makes sense in the Mainsail-hosted build. */
export function showMainsailLink(): boolean {
  return isMainsailHost()
}

export interface BackUi {
  /** Detected UI name ('Mainsail' | 'Fluidd') or '' when unknown (caller shows a generic label). */
  name: string
  /** Host-preserving URL to return to (origin root, or VITE_MAINSAIL_URL). */
  url: string
}

interface DetectOpts {
  url?: string
  fetchImpl?: typeof fetch
  timeoutMs?: number
  location?: { protocol?: string; hostname?: string }
}

/**
 * Best-effort detection of the printer's primary web UI for a host-preserving "back" link.
 * Probes the candidate origin's `manifest.json` for a Mainsail/Fluidd name; ANY failure (no
 * fetch, CORS, timeout, non-200, unknown name) resolves to a generic `{ name: '' }` - never throws.
 */
export async function detectBackUi(opts: DetectOpts = {}): Promise<BackUi> {
  const loc =
    opts.location ??
    (typeof window !== 'undefined' ? window.location : { protocol: 'http:', hostname: 'localhost' })
  const url = opts.url ?? `${loc.protocol ?? 'http:'}//${loc.hostname ?? 'localhost'}/`
  const f = opts.fetchImpl ?? (typeof fetch !== 'undefined' ? fetch : undefined)
  if (!f) return { name: '', url }

  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : undefined
  const timer = ctrl ? setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 2000) : undefined
  try {
    const res = await f(`${url}manifest.json`, ctrl ? { signal: ctrl.signal } : {})
    if (!res.ok) return { name: '', url }
    const data = (await res.json()) as { name?: unknown }
    const raw = typeof data.name === 'string' ? data.name : ''
    const name = /mainsail/i.test(raw) ? 'Mainsail' : /fluidd/i.test(raw) ? 'Fluidd' : ''
    return { name, url }
  } catch {
    return { name: '', url }
  } finally {
    if (timer) clearTimeout(timer)
  }
}

// Per-host widget visibility. Some widgets need the FilaMind 3D host. In the Mainsail build the
// GATED ones still appear but render an install-required panel (see widgets/index.ts) instead of
// their UI; in the suite build they run normally. (Screen-only tools like the FilaMind-screen
// command tab live inside Screen Manager and gate themselves at the tab level.)
const SUITE_GATED = new Set<string>([
  'material-brain',
  'tuning',
  'preflight',
  'known-good-pack',
  'rules',
])
const SUITE_HIDDEN = new Set<string>([])

/** Whether a widget should register under the current host (hidden ones drop out in Mainsail). */
export function isWidgetEnabled(id: string): boolean {
  if (SUITE_HIDDEN.has(id)) return isSuiteHost()
  return true
}

/** Whether a registered widget should show the install-required panel instead of its real UI. */
export function isWidgetGated(id: string): boolean {
  return SUITE_GATED.has(id) && !isSuiteHost()
}
