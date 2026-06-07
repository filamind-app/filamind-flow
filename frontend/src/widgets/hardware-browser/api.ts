import { resolveEndpoints } from '@/core/moonraker'

import type {
  BoardDetail,
  BoardsResult,
  DriverDetail,
  DriversResult,
  HardwareCategories,
  HardwareSearchResult,
} from './types'

export interface SearchParams {
  q?: string
  category?: string
  manufacturer?: string
  limit?: number
  offset?: number
}

/** Search the curated hardware DB (filtered + paginated). */
export async function searchHardware(params: SearchParams): Promise<HardwareSearchResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.category) qs.set('category', params.category)
  if (params.manufacturer) qs.set('manufacturer', params.manufacturer)
  qs.set('limit', String(params.limit ?? 25))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware?${qs.toString()}`)
  if (!response.ok) throw new Error(`Hardware search failed (${response.status})`)
  return (await response.json()) as HardwareSearchResult
}

/** The hardware categories + total component count (for the filters). */
export async function fetchCategories(): Promise<HardwareCategories> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/hardware/categories`)
  if (!response.ok) throw new Error(`Categories request failed (${response.status})`)
  return (await response.json()) as HardwareCategories
}

/** Search the canonical board catalog (summaries, paginated). */
export async function fetchBoards(params: {
  q?: string
  manufacturer?: string
  limit?: number
  offset?: number
}): Promise<BoardsResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.manufacturer) qs.set('manufacturer', params.manufacturer)
  qs.set('limit', String(params.limit ?? 24))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware/boards?${qs.toString()}`)
  if (!response.ok) throw new Error(`Boards request failed (${response.status})`)
  return (await response.json()) as BoardsResult
}

/** The full board record (specs + aggregated ports[] + media). */
export async function fetchBoardDetail(boardId: string): Promise<BoardDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/hardware/boards/${encodeURIComponent(boardId)}`)
  if (!response.ok) throw new Error(`Board request failed (${response.status})`)
  return (await response.json()) as BoardDetail
}

/** Search the canonical driver catalog (summaries, paginated). */
export async function fetchDrivers(params: {
  q?: string
  manufacturer?: string
  klipperOnly?: boolean
  limit?: number
  offset?: number
}): Promise<DriversResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.manufacturer) qs.set('manufacturer', params.manufacturer)
  if (params.klipperOnly) qs.set('klipper_only', 'true')
  qs.set('limit', String(params.limit ?? 24))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware/drivers?${qs.toString()}`)
  if (!response.ok) throw new Error(`Drivers request failed (${response.status})`)
  return (await response.json()) as DriversResult
}

/** The full driver record (specs + Klipper support + copyable config snippet). */
export async function fetchDriverDetail(driverId: string): Promise<DriverDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/hardware/drivers/${encodeURIComponent(driverId)}`)
  if (!response.ok) throw new Error(`Driver request failed (${response.status})`)
  return (await response.json()) as DriverDetail
}
