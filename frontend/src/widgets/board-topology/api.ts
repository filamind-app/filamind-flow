import { resolveEndpoints } from '@/core/moonraker'

import type { BoardDetail, PinAtlas, Topology } from './types'

/** Host → MCU topology from the live config (read-only). */
export async function fetchTopology(): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology`)
  if (!response.ok) {
    throw new Error(`Topology request failed (${response.status})`)
  }
  return (await response.json()) as Topology
}

/** Confirm / override the catalog board for one MCU (keyed by its config section name). Persisted
 *  on the host and applied to every future read; returns the refreshed topology. */
export async function setBoardOverride(mcuName: string, boardId: string): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mcu_name: mcuName, board_id: boardId }),
  })
  if (!response.ok) {
    throw new Error(`Board override failed (${response.status})`)
  }
  return (await response.json()) as Topology
}

/** The used-vs-free pin map of an MCU's resolved board + wiring-health findings. */
export async function fetchPinAtlas(mcuName: string): Promise<PinAtlas> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/topology/pin-atlas/${encodeURIComponent(mcuName)}`,
  )
  if (!response.ok) {
    throw new Error(`Pin atlas request failed (${response.status})`)
  }
  return (await response.json()) as PinAtlas
}

/** Clear an MCU's board override (revert to the auto suggestion); returns the refreshed topology. */
export async function clearBoardOverride(mcuName: string): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/override/clear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mcu_name: mcuName }),
  })
  if (!response.ok) {
    throw new Error(`Clear override failed (${response.status})`)
  }
  return (await response.json()) as Topology
}

/** The full catalog record for a detected board (aggregated ports + specs) plus its cross-entity
 *  links (manufacturer / MCU(s) / drivers / …) inlined via the DB linking graph in one round-trip. */
export async function fetchBoardDetail(boardId: string): Promise<BoardDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/hardware/boards/${encodeURIComponent(boardId)}?expand=related`,
  )
  if (!response.ok) {
    throw new Error(`Board request failed (${response.status})`)
  }
  return (await response.json()) as BoardDetail
}
