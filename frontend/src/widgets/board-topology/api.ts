import { resolveEndpoints } from '@/core/moonraker'

import type { Topology } from './types'

/** Host → MCU topology from the live config (read-only). */
export async function fetchTopology(): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology`)
  if (!response.ok) {
    throw new Error(`Topology request failed (${response.status})`)
  }
  return (await response.json()) as Topology
}
