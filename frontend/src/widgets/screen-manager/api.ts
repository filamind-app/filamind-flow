import { httpError } from '@/core/describeError'
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
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as ScreenStatus
}

/** Read KlipperScreen.conf (raw text + sha256 fingerprint). */
export async function fetchScreenConf(): Promise<ScreenConf> {
  const r = await fetch(`${base()}/api/screen/conf`)
  if (!r.ok) throw new Error(httpError(r.status))
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
  if (!r.ok) throw new ScreenSaveError(body.detail || httpError(r.status), r.status)
  return body as ScreenConf
}

/** Restart the KlipperScreen service so the saved config takes effect. */
export async function restartScreen(): Promise<void> {
  const r = await fetch(`${base()}/api/screen/restart`, { method: 'POST' })
  if (!r.ok) throw new Error(httpError(r.status))
}

// ── Graphical [main] options (Settings form) ──────────────────────────────────

export interface ScreenOptions {
  options: Record<string, string>
  sha256: string | null
}

/** Current `[main]` options (key → value) + the conf fingerprint, for the form editor. */
export async function fetchScreenOptions(): Promise<ScreenOptions> {
  const r = await fetch(`${base()}/api/screen/options`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as ScreenOptions
}

/** Set `[main]` options (gated save; adds/replaces each, #~# preserved). Throws ScreenSaveError. */
export async function saveScreenOptions(
  options: Record<string, string>,
  expectedSha256: string | null,
): Promise<ScreenConf> {
  const r = await fetch(`${base()}/api/screen/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ options, expected_sha256: expectedSha256 }),
  })
  const body = (await r.json().catch(() => ({}))) as { detail?: string } & Partial<ScreenConf>
  if (!r.ok) throw new ScreenSaveError(body.detail || httpError(r.status), r.status)
  return body as ScreenConf
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
  return b.detail || httpError(r.status)
}

/** Installed themes + the palette token schema + default colors. */
export async function fetchThemes(): Promise<ThemeCatalog> {
  const r = await fetch(`${base()}/api/screen/themes`)
  if (!r.ok) throw new Error(httpError(r.status))
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

// ── Menu tree editor ─────────────────────────────────────────────────────────

export interface MenuItem {
  id: string
  tree: string
  parent: string
  props: Record<string, string>
}

export interface MenuCatalog {
  items: MenuItem[]
  panels: string[]
  sha256: string | null
}

/** The menu tree (flat items) + the panels a button can open. */
export async function fetchMenus(): Promise<MenuCatalog> {
  const r = await fetch(`${base()}/api/screen/menus`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as MenuCatalog
}

/** Rewrite the whole menu set (gated save). Throws ScreenSaveError(status) on busy/stale. */
export async function saveMenus(
  items: { id: string; props: Record<string, string> }[],
  expectedSha256: string | null,
): Promise<ScreenConf> {
  const r = await fetch(`${base()}/api/screen/menus`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, expected_sha256: expectedSha256 }),
  })
  const body = (await r.json().catch(() => ({}))) as { detail?: string } & Partial<ScreenConf>
  if (!r.ok) throw new ScreenSaveError(body.detail || httpError(r.status), r.status)
  return body as ScreenConf
}

// ── FilaMind Kiosk ─────────────────────────────────────────────────────────────

export interface KioskStatus {
  /** Which service currently owns the touchscreen. */
  mode: 'kiosk' | 'klipperscreen' | 'none'
  kiosk_installed: boolean
  kiosk_active: boolean
  kiosk_enabled: boolean
  screen_installed: boolean
  screen_active: boolean
  /** The on-host URL the kiosk browser opens. */
  url: string
}

/** Current screen mode + whether the kiosk is installed / active / boot-enabled. */
export async function fetchKioskStatus(): Promise<KioskStatus> {
  const r = await fetch(`${base()}/api/screen/kiosk`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as KioskStatus
}

/** Put FilaMind on the touchscreen. `persist` also makes it the boot default. */
export async function switchToKiosk(persist: boolean): Promise<KioskStatus> {
  const r = await fetch(`${base()}/api/screen/kiosk/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persist }),
  })
  if (!r.ok) throw new Error(await detailOf(r))
  const body = (await r.json()) as { status: KioskStatus }
  return body.status
}

/** Hand the touchscreen back to KlipperScreen. `persist` also makes it the boot default. */
export async function restoreScreen(persist: boolean): Promise<KioskStatus> {
  const r = await fetch(`${base()}/api/screen/kiosk/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persist }),
  })
  if (!r.ok) throw new Error(await detailOf(r))
  const body = (await r.json()) as { status: KioskStatus }
  return body.status
}

// ── Touchscreen selector (KlipperScreen / Guppyscreen / FilaMind) ───────────────

export type TouchKey = 'klipperscreen' | 'guppyscreen' | 'filamind-screen' | 'filamind-flow'

export interface TouchScreen {
  unit: string
  installed: boolean
  /** True only for systemd-unit-backed UIs that can be switched from here (a clone-only UI like
   *  Guppyscreen reads installed:true but manageable:false). */
  manageable: boolean
  active: boolean
  enabled: boolean
}

export interface TouchStatus {
  /** Which touch UI currently owns the display ('none' if none active). */
  active: TouchKey | 'none'
  screens: Record<TouchKey, TouchScreen>
  url: string
}

/** All touch UIs: installed / active / boot-enabled + which one owns the display. */
export async function fetchTouchStatus(): Promise<TouchStatus> {
  const r = await fetch(`${base()}/api/screen/touch`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as TouchStatus
}

/** Switch which touch UI runs (optionally as the boot default). */
export async function switchTouch(target: TouchKey, persist: boolean): Promise<TouchStatus> {
  const r = await fetch(`${base()}/api/screen/touch/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, persist }),
  })
  if (!r.ok) throw new Error(await detailOf(r))
  return (await r.json()).status as TouchStatus
}
