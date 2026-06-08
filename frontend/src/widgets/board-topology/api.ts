import { resolveEndpoints } from '@/core/moonraker'

import type { BoardDetail, Topology } from './types'

/** Host → MCU topology from the live config (read-only). */
export async function fetchTopology(): Promise<Topology> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/topology`)
  if (!response.ok) {
    throw new Error(`Topology request failed (${response.status})`)
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
