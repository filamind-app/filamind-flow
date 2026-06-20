// Single-source DUAL-HOST adapter. One build runs either:
//   - 'mainsail' (default): the current Mainsail-integrated sidebar deployment, or
//   - 'suite':   hosted inside the FilaMind suite,
// selected by the VITE_HOST_MODE build flag. There are no long-lived branches — host-specific
// behaviour funnels through this module so the rest of the app stays host-agnostic.
//
// Policy: new flow innovations are SUITE-exclusive (the Mainsail build stays feature-frozen);
// the few cross-host essentials (e.g. Setup) ship in BOTH. Connection URLs are NOT decided here —
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

/** The "back to Mainsail" link only makes sense in the Mainsail-hosted build. */
export function showMainsailLink(): boolean {
  return isMainsailHost()
}

// Per-host widget visibility. New flow innovations are SUITE-exclusive (the differentiation moat):
// the Mainsail build stays feature-frozen. `remote-control` (steer the on-printer FilaMind screen)
// only makes sense in the suite, where that screen exists, so it ships suite-only.
const SUITE_ONLY = new Set<string>(['remote-control'])
const MAINSAIL_ONLY = new Set<string>([])

/** Whether a widget should register under the current host. */
export function isWidgetEnabled(id: string): boolean {
  if (SUITE_ONLY.has(id)) return isSuiteHost()
  if (MAINSAIL_ONLY.has(id)) return isMainsailHost()
  return true
}
