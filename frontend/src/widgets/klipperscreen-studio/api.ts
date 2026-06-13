import { resolveEndpoints } from '@/core/moonraker'

import type { ScreenConf, ScreenStatus } from './types'

/** A save error carrying the HTTP status so the UI can tell busy (409) from stale (412). */
export class ScreenSaveError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ScreenSaveError'
  }
}

function base(): string {
  return resolveEndpoints().backendUrl
}

/** Is KlipperScreen present + restartable, and its current theme/language. */
export async function fetchScreenStatus(): Promise<ScreenStatus> {
  const r = await fetch(`${base()}/api/screen/status`)
  if (!r.ok) throw new Error(`Status check failed (${r.status})`)
  return (await r.json()) as ScreenStatus
}

/** Read KlipperScreen.conf (raw text + sha256 fingerprint). */
export async function fetchScreenConf(): Promise<ScreenConf> {
  const r = await fetch(`${base()}/api/screen/conf`)
  if (!r.ok) throw new Error(`Could not read KlipperScreen.conf (${r.status})`)
  return (await r.json()) as ScreenConf
}

/** Gated save. Throws ScreenSaveError(status) on busy (409) / stale (412) / bad input (400). */
export async function saveScreenConf(
  content: string,
  expectedSha256: string | null,
): Promise<ScreenConf> {
  const r = await fetch(`${base()}/api/screen/conf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, expected_sha256: expectedSha256 }),
  })
  const body = (await r.json().catch(() => ({}))) as { detail?: string } & Partial<ScreenConf>
  if (!r.ok) throw new ScreenSaveError(body.detail || `Save failed (${r.status})`, r.status)
  return body as ScreenConf
}

/** Restart the KlipperScreen service so the saved config takes effect. */
export async function restartScreen(): Promise<void> {
  const r = await fetch(`${base()}/api/screen/restart`, { method: 'POST' })
  if (!r.ok) throw new Error(`Restart failed (${r.status})`)
}

// ── Theme builder ────────────────────────────────────────────────────────────

export interface ScreenTheme {
  name: string
  generated: boolean
}

export interface ThemeCatalog {
  themes: ScreenTheme[]
  tokens: string[]
  defaults: Record<string, string>
}

async function detailOf(r: Response): Promise<string> {
  const b = (await r.json().catch(() => ({}))) as { detail?: string }
  return b.detail || `Request failed (${r.status})`
}

/** Installed themes + the palette token schema + default colors. */
export async function fetchThemes(): Promise<ThemeCatalog> {
  const r = await fetch(`${base()}/api/screen/themes`)
  if (!r.ok) throw new Error(`Could not list themes (${r.status})`)
  return (await r.json()) as ThemeCatalog
}

/** Generate + write a theme folder host-side. */
export async function createTheme(
  name: string,
  palette: Record<string, string>,
  radius: number,
): Promise<void> {
  const r = await fetch(`${base()}/api/screen/themes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, palette, radius }),
  })
  if (!r.ok) throw new Error(await detailOf(r))
}

/** Set this theme as the active one in KlipperScreen.conf (a restart applies it). */
export async function activateTheme(name: string): Promise<void> {
  const r = await fetch(`${base()}/api/screen/themes/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error(await detailOf(r))
}

/** Delete a FilaMind-generated theme. */
export async function deleteTheme(name: string): Promise<void> {
  const r = await fetch(`${base()}/api/screen/themes/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error(await detailOf(r))
}
