import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { SetupActionResult, SetupAutoUpdate, SetupCatalog, SetupStatus } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

/** A setup-action error carrying the HTTP status so the UI can tell refused (403) from other faults. */
export class SetupActionError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'SetupActionError'
  }
}

/** The component catalog (groups → components). */
export async function fetchCatalog(): Promise<SetupCatalog> {
  const r = await fetch(`${base()}/api/setup/catalog`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupCatalog
}

/** Installed status per component + whether GUI writes are enabled on this host. */
export async function fetchStatus(): Promise<SetupStatus> {
  const r = await fetch(`${base()}/api/setup/status`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupStatus
}

async function post(path: string, body: unknown): Promise<SetupActionResult> {
  const r = await fetch(`${base()}/api/setup/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await r.json().catch(() => ({}))) as { detail?: string } & SetupActionResult
  if (!r.ok) throw new SetupActionError(data.detail || httpError(r.status), r.status)
  return data
}

export const installComponent = (id: string, port?: number): Promise<SetupActionResult> =>
  post('install', { id, ...(port ? { port } : {}) })

/** Start an install as a background task; returns its id to poll via fetchTask(). An optional port
 *  installs a first-party web app (e.g. FilaMind 3d) straight onto that port; `action: 'service'`
 *  installs that app's additional managed deployment (FilaMind 3d → the agent). Refusals (403)
 *  still arrive synchronously as a SetupActionError, same as the blocking install. */
export async function installComponentStream(
  id: string,
  port?: number,
  action?: string,
): Promise<string> {
  const r = await fetch(`${base()}/api/setup/install/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, ...(port ? { port } : {}), ...(action ? { action } : {}) }),
  })
  const data = (await r.json().catch(() => ({}))) as { detail?: string; task_id?: string }
  if (!r.ok) throw new SetupActionError(data.detail || httpError(r.status), r.status)
  return data.task_id ?? ''
}

export const updateComponent = (id: string): Promise<SetupActionResult> => post('update', { id })
/** Restart a component's runtime (reload nginx for a first-party app, or restart its service). */
export const restartComponent = (id: string): Promise<SetupActionResult> => post('restart', { id })
export const removeComponent = (id: string, confirm: string): Promise<SetupActionResult> =>
  post('remove', { id, confirm })
export const setPort = (id: string, port: number): Promise<SetupActionResult> =>
  post('port', { id, port })
/** The last lines of a component's systemd journal (read-only) - debug a failed install/start. */
export const fetchLogs = (id: string): Promise<SetupActionResult> => post('logs', { id })
/** Register an installed unmanaged git checkout with Moonraker's update manager. */
export const registerComponent = (id: string): Promise<SetupActionResult> =>
  post('register', { id })
/** Wire an add-on into printer.cfg (add=true) or remove its `[include]` (add=false). */
export const toggleInclude = (id: string, add: boolean): Promise<SetupActionResult> =>
  post('include', { id, add })

/** Enable/disable installing from the widget itself (persisted; no CLI/env needed). */
export async function setWrites(enabled: boolean): Promise<boolean> {
  const r = await fetch(`${base()}/api/setup/writes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return ((await r.json()) as { writesEnabled: boolean }).writesEnabled
}

/** Current periodic auto-update preferences. */
export async function getAutoUpdate(): Promise<SetupAutoUpdate> {
  const r = await fetch(`${base()}/api/setup/autoupdate`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupAutoUpdate
}

/** Persist the auto-update toggle + interval; returns the saved prefs. */
export async function setAutoUpdate(
  enabled: boolean,
  intervalHours: number,
): Promise<SetupAutoUpdate> {
  const r = await fetch(`${base()}/api/setup/autoupdate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, intervalHours }),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupAutoUpdate
}
