import { resolveEndpoints } from '@/core/moonraker'

import type { BoardDiscovery, FirmwareStatus } from './types'

/** Fetches read-only firmware status from the FilaMind backend. */
export async function fetchFirmwareStatus(): Promise<FirmwareStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/status`)
  if (!response.ok) {
    throw new Error(`Firmware status request failed (${response.status})`)
  }
  return (await response.json()) as FirmwareStatus
}

/** Discovers every flashable board on the host (Moonraker + USB/CAN/DFU scans). */
export async function fetchBoards(): Promise<BoardDiscovery> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/boards`)
  if (!response.ok) {
    throw new Error(`Board discovery failed (${response.status})`)
  }
  return (await response.json()) as BoardDiscovery
}
