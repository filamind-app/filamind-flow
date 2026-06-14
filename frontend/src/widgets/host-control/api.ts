import { resolveEndpoints } from '@/core/moonraker'

import type {
  CleanupRunResult,
  CleanupTarget,
  HostMonitor,
  NetworkSetReq,
  PowerAction,
  ServiceAction,
  ServiceActionResult,
  ServiceDetail,
  ServiceUnit,
  SystemActionResult,
  SystemInfo,
} from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

/** A host-action error carrying the HTTP status so the UI can tell refused (403) from other faults. */
export class HostActionError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'HostActionError'
  }
}

/** Read-only snapshot of host health + OS state (CPU / memory / disk / network / time / locale). */
export async function fetchMonitor(): Promise<HostMonitor> {
  const r = await fetch(`${base()}/api/host/monitor`)
  if (!r.ok) throw new Error(`Host monitor failed (${r.status})`)
  return (await r.json()) as HostMonitor
}

// ── Services (Phase 2) ─────────────────────────────────────────────────────────

/** All systemd .service units with their state (read-only). */
export async function fetchServices(): Promise<ServiceUnit[]> {
  const r = await fetch(`${base()}/api/host/services`)
  if (!r.ok) throw new Error(`Could not list services (${r.status})`)
  return ((await r.json()) as { services: ServiceUnit[] }).services
}

/** Per-unit detail + whether its unit file is safe to delete. */
export async function fetchServiceDetail(name: string): Promise<ServiceDetail> {
  const r = await fetch(`${base()}/api/host/services/detail?name=${encodeURIComponent(name)}`)
  if (!r.ok) throw new Error(`Could not read service detail (${r.status})`)
  return (await r.json()) as ServiceDetail
}

/** Recent journal lines for a unit (read-only). */
export async function fetchServiceLogs(name: string, lines = 200): Promise<string> {
  const r = await fetch(
    `${base()}/api/host/services/logs?name=${encodeURIComponent(name)}&lines=${lines}`,
  )
  if (!r.ok) throw new Error(`Could not read logs (${r.status})`)
  return ((await r.json()) as { logs: string }).logs
}

async function postAction(path: string, body: unknown): Promise<ServiceActionResult> {
  const r = await fetch(`${base()}/api/host/services/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await r.json().catch(() => ({}))) as {
    detail?: string
  } & Partial<ServiceActionResult>
  if (!r.ok) throw new HostActionError(data.detail || `Action failed (${r.status})`, r.status)
  return data as ServiceActionResult
}

/** Run a systemctl action on a unit. Throws HostActionError(403) if the backend refuses it. */
export async function serviceAction(
  name: string,
  action: ServiceAction,
): Promise<ServiceActionResult> {
  return postAction('action', { name, action })
}

/** Remove a user-installed unit file (typed-confirm). Throws HostActionError(403) if refused. */
export async function deleteService(name: string, confirm: string): Promise<ServiceActionResult> {
  return postAction('delete', { name, confirm })
}

// ── Disk cleanup (Phase 3) ─────────────────────────────────────────────────────

/** Dry-run: how much each cleanup target would free (no deletion). */
export async function fetchCleanup(): Promise<CleanupTarget[]> {
  const r = await fetch(`${base()}/api/host/cleanup`)
  if (!r.ok) throw new Error(`Could not scan disk (${r.status})`)
  return ((await r.json()) as { targets: CleanupTarget[] }).targets
}

/** Clean the requested targets and report the space reclaimed. */
export async function runCleanup(ids: string[]): Promise<CleanupRunResult> {
  const r = await fetch(`${base()}/api/host/cleanup/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
  const data = (await r.json().catch(() => ({}))) as { detail?: string } & Partial<CleanupRunResult>
  if (!r.ok) throw new HostActionError(data.detail || `Cleanup failed (${r.status})`, r.status)
  return data as CleanupRunResult
}

// ── System settings (Phase 4) ──────────────────────────────────────────────────

/** Current time/locale/hostname/Wi-Fi settings + the option lists for the System form. */
export async function fetchSystemInfo(): Promise<SystemInfo> {
  const r = await fetch(`${base()}/api/host/system`)
  if (!r.ok) throw new Error(`Could not read system settings (${r.status})`)
  return (await r.json()) as SystemInfo
}

async function postSystem(path: string, body: unknown): Promise<SystemActionResult> {
  const r = await fetch(`${base()}/api/host/system/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await r.json().catch(() => ({}))) as {
    detail?: string
  } & Partial<SystemActionResult>
  if (!r.ok) throw new HostActionError(data.detail || `Failed (${r.status})`, r.status)
  return data as SystemActionResult
}

export const setTimezone = (timezone: string) => postSystem('timezone', { timezone })
export const setNtp = (enabled: boolean) => postSystem('ntp', { enabled })
export const setTime = (value: string) => postSystem('time', { value })
export const setLocaleLang = (lang: string) => postSystem('locale', { lang })
export const setKeymap = (keymap: string) => postSystem('keymap', { keymap })
export const setHostname = (hostname: string) => postSystem('hostname', { hostname })
export const setWifi = (ssid: string, password: string) => postSystem('wifi', { ssid, password })
export const power = (action: PowerAction) => postSystem('power', { action })
/** Switch the panel's active connection to DHCP (auto) or a static IPv4 (manual). */
export const setNetwork = (req: NetworkSetReq) => postSystem('network', req)
