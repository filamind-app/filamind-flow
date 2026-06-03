import { resolveEndpoints } from '@/core/moonraker'

import type { DriversStatus } from './types'

/** Fetches the read-only TMC driver inventory from the FilaMind backend. */
export async function fetchDriverStatus(): Promise<DriversStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/drivers/status`)
  if (!response.ok) {
    throw new Error(`Driver status request failed (${response.status})`)
  }
  return (await response.json()) as DriversStatus
}
