import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type {
  BootInfo,
  CanBusActionResult,
  CanBusStatus,
  CleanupRunResult,
  CleanupTarget,
  HealthAdvisory,
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
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as HostMonitor
}

/** Graded host-health cards (CPU / memory / disk / clock / services), read-only. */
export async function fetchAdvisor(): Promise<HealthAdvisory> {
  const r = await fetch(`${base()}/api/host/advisor`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as HealthAdvisory
}

// -- Boot -----------------------------------------------------------------------

/** Read-only boot config: default systemd target, active boot splash, plymouth theme. */
export async function fetchBootInfo(): Promise<BootInfo> {
  const r = await fetch(`${base()}/api/host/boot`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as BootInfo
}

/** URL of the active boot-splash image, for an <img> preview (cache-busted per load). */
export function bootSplashUrl(): string {
  return `${base()}/api/host/boot/splash?t=${Date.now()}`
}

/** Write a new boot-splash PNG (base64 / data URL). Throws HostActionError(403) if refused. */
export async function setBootSplash(image: string, target?: string): Promise<SystemActionResult> {
  const r = await fetch(`${base()}/api/host/boot/splash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image, ...(target ? { target } : {}) }),
  })
  const data = (await r.json().catch(() => ({}))) as {
    detail?: string
  } & Partial<SystemActionResult>
  if (!r.ok) throw new HostActionError(data.detail || httpError(r.status), r.status)
  return data as SystemActionResult
}

// -- Services (Phase 2) ---------------------------------------------------------

/** All systemd .service units with their state (read-only). */
export async function fetchServices(): Promise<ServiceUnit[]> {
  const r = await fetch(`${base()}/api/host/services`)
  if (!r.ok) throw new Error(httpError(r.status))
  return ((await r.json()) as { services: ServiceUnit[] }).services
}

/** Per-unit detail + whether its unit file is safe to delete. */
export async function fetchServiceDetail(name: string): Promise<ServiceDetail> {
  const r = await fetch(`${base()}/api/host/services/detail?name=${encodeURIComponent(name)}`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as ServiceDetail
}

/** Recent journal lines for a unit (read-only). */
export async function fetchServiceLogs(name: string, lines = 200): Promise<string> {
  const r = await fetch(
    `${base()}/api/host/services/logs?name=${encodeURIComponent(name)}&lines=${lines}`,
  )
  if (!r.ok) throw new Error(httpError(r.status))
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
  if (!r.ok) throw new HostActionError(data.detail || httpError(r.status), r.status)
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

// -- Disk cleanup (Phase 3) -----------------------------------------------------

/** Dry-run: how much each cleanup target would free (no deletion). */
export async function fetchCleanup(): Promise<CleanupTarget[]> {
  const r = await fetch(`${base()}/api/host/cleanup`)
  if (!r.ok) throw new Error(httpError(r.status))
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
  if (!r.ok) throw new HostActionError(data.detail || httpError(r.status), r.status)
  return data as CleanupRunResult
}

// -- System settings (Phase 4) --------------------------------------------------

/** Current time/locale/hostname/network settings + the option lists for the System form. */
export async function fetchSystemInfo(): Promise<SystemInfo> {
  const r = await fetch(`${base()}/api/host/system`)
  if (!r.ok) throw new Error(httpError(r.status))
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
  if (!r.ok) throw new HostActionError(data.detail || httpError(r.status), r.status)
  return data as SystemActionResult
}

// -- CAN bus control (Phase 5) --------------------------------------------------

/** Every host CAN interface with live status + bridging-adapter link (read-only). */
export async function fetchCanBuses(): Promise<CanBusStatus[]> {
  const r = await fetch(`${base()}/api/host/canbus`)
  if (!r.ok) throw new Error(httpError(r.status))
  return ((await r.json()) as { buses: CanBusStatus[] }).buses
}

async function postCanbus(path: string, body: unknown): Promise<CanBusActionResult> {
  const r = await fetch(`${base()}/api/host/canbus/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await r.json().catch(() => ({}))) as {
    detail?: string
  } & Partial<CanBusActionResult>
  if (!r.ok) throw new HostActionError(data.detail || httpError(r.status), r.status)
  return data as CanBusActionResult
}

/** Bring a CAN interface up or down. Throws HostActionError(403) if refused (e.g. printing). */
export const setCanLink = (iface: string, up: boolean) => postCanbus('link', { iface, up })
/** Set a CAN interface's bitrate (interface must be down first). Throws HostActionError if refused. */
export const setCanBitrate = (iface: string, bitrate: number) =>
  postCanbus('bitrate', { iface, bitrate })
/** Set any combination of CAN parameters (timing/modes/recovery/CAN-FD/txqueuelen). All but
 *  txqueuelen need the interface down. Throws HostActionError(400) on a bad value, (403) if refused. */
export const setCanParams = (iface: string, params: Record<string, number | boolean>) =>
  postCanbus('params', { iface, params })
/** Restart a BUS-OFF CAN controller to recover the bus. Throws HostActionError if refused. */
export const restartCanBus = (iface: string) => postCanbus('restart', { iface })

export const setTimezone = (timezone: string) => postSystem('timezone', { timezone })
export const setNtp = (enabled: boolean) => postSystem('ntp', { enabled })
export const setTime = (value: string) => postSystem('time', { value })
export const setLocaleLang = (lang: string) => postSystem('locale', { lang })
export const setKeymap = (keymap: string) => postSystem('keymap', { keymap })
export const setHostname = (hostname: string) => postSystem('hostname', { hostname })
export const power = (action: PowerAction) => postSystem('power', { action })
/** Switch the panel's active connection to DHCP (auto) or a static IPv4 (manual). */
export const setNetwork = (req: NetworkSetReq) => postSystem('network', req)
