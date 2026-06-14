import { resolveEndpoints } from '@/core/moonraker'

import type { HostMonitor } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

/** Read-only snapshot of host health + OS state (CPU / memory / disk / network / time / locale). */
export async function fetchMonitor(): Promise<HostMonitor> {
  const r = await fetch(`${base()}/api/host/monitor`)
  if (!r.ok) throw new Error(`Host monitor failed (${r.status})`)
  return (await r.json()) as HostMonitor
}
