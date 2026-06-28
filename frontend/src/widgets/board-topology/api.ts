import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type {
  BoardDetail,
  CanDfuStatus,
  CanFlashResult,
  CanFlashRevision,
  PinAtlas,
  Topology,
  TopologyDiff,
} from './types'

/** Host → MCU topology from the live config (read-only). */
export async function fetchTopology(): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology`)
  if (!response.ok) {
    throw new Error(httpError(response.status))
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
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as Topology
}

/** Save the current topology as the hardware baseline (for later change detection). */
export async function saveSnapshot(): Promise<TopologyDiff> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/snapshot`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as TopologyDiff
}

/** Compare the live topology to the saved baseline (board swapped / MCU added/removed / …). */
export async function fetchDiff(): Promise<TopologyDiff> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/snapshot/diff`)
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as TopologyDiff
}

/** The used-vs-free pin map of an MCU's resolved board + wiring-health findings. */
export async function fetchPinAtlas(mcuName: string): Promise<PinAtlas> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/topology/pin-atlas/${encodeURIComponent(mcuName)}`,
  )
  if (!response.ok) {
    throw new Error(httpError(response.status))
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
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as Topology
}

/** The selectable USB-CAN adapter revisions (U2C v1 / v2) for the flash picker. */
export async function fetchCanRevisions(): Promise<CanFlashRevision[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/canbus/firmware`)
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  const data = (await response.json()) as { revisions?: CanFlashRevision[] }
  return data.revisions ?? []
}

/** Whether the adapter is currently in its STM32 ROM-DFU bootloader (polled during the guided flash). */
export async function fetchDfuStatus(): Promise<CanDfuStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/canbus/dfu-status`)
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as CanDfuStatus
}

/** Flash the chosen revision's official firmware to the adapter sitting in DFU (gated server-side). */
export async function flashCanAdapter(revision: string): Promise<CanFlashResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology/canbus/flash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ revision }),
  })
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as CanFlashResult
}

/** The full catalog record for a detected board (aggregated ports + specs) plus its cross-entity
 *  links (manufacturer / MCU(s) / drivers / …) inlined via the DB linking graph in one round-trip. */
export async function fetchBoardDetail(boardId: string): Promise<BoardDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/hardware/boards/${encodeURIComponent(boardId)}?expand=related`,
  )
  if (!response.ok) {
    throw new Error(httpError(response.status))
  }
  return (await response.json()) as BoardDetail
}
