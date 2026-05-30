import { resolveEndpoints } from '@/core/moonraker'

import type { FirmwareStatus } from './types'

/** Fetches read-only firmware status from the FilaMind backend. */
export async function fetchFirmwareStatus(): Promise<FirmwareStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/status`)
  if (!response.ok) {
    throw new Error(`Firmware status request failed (${response.status})`)
  }
  return (await response.json()) as FirmwareStatus
}
