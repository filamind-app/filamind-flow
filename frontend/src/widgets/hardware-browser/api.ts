import { resolveEndpoints } from '@/core/moonraker'

import type {
  BoardDetail,
  BoardsResult,
  CatalogEntityDetail,
  CatalogResult,
  DriverDetail,
  DriversResult,
  HardwareCategories,
  HardwareSearchResult,
  HostDetail,
  HostsResult,
  MotorDetail,
  MotorsResult,
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

/** Search the canonical motor catalog (summaries, paginated). */
export async function fetchMotors(params: {
  q?: string
  manufacturer?: string
  nema?: string
  limit?: number
  offset?: number
}): Promise<MotorsResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.manufacturer) qs.set('manufacturer', params.manufacturer)
  if (params.nema) qs.set('nema', params.nema)
  qs.set('limit', String(params.limit ?? 24))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware/motors?${qs.toString()}`)
  if (!response.ok) throw new Error(`Motors request failed (${response.status})`)
  return (await response.json()) as MotorsResult
}

/** The full motor record (specs + recommended run_current + presets + config snippet). */
export async function fetchMotorDetail(motorId: string): Promise<MotorDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/hardware/motors/${encodeURIComponent(motorId)}`)
  if (!response.ok) throw new Error(`Motor request failed (${response.status})`)
  return (await response.json()) as MotorDetail
}

/** Search the canonical host-computer catalog (summaries, paginated). */
export async function fetchHosts(params: {
  q?: string
  manufacturer?: string
  kind?: string
  limit?: number
  offset?: number
}): Promise<HostsResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.manufacturer) qs.set('manufacturer', params.manufacturer)
  if (params.kind) qs.set('kind', params.kind)
  qs.set('limit', String(params.limit ?? 24))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware/hosts?${qs.toString()}`)
  if (!response.ok) throw new Error(`Hosts request failed (${response.status})`)
  return (await response.json()) as HostsResult
}

/** The full host record (specs + Klipper-open flag + copyable host config snippet). */
export async function fetchHostDetail(hostId: string): Promise<HostDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/hardware/hosts/${encodeURIComponent(hostId)}`)
  if (!response.ok) throw new Error(`Host request failed (${response.status})`)
  return (await response.json()) as HostDetail
}

/** Search one category's canonical catalog entities (summaries, paginated). */
export async function fetchCatalog(params: {
  category: string
  q?: string
  limit?: number
  offset?: number
}): Promise<CatalogResult> {
  const { backendUrl } = resolveEndpoints()
  const qs = new URLSearchParams()
  qs.set('category', params.category)
  if (params.q) qs.set('q', params.q)
  qs.set('limit', String(params.limit ?? 24))
  qs.set('offset', String(params.offset ?? 0))
  const response = await fetch(`${backendUrl}/api/hardware/catalog?${qs.toString()}`)
  if (!response.ok) throw new Error(`Catalog request failed (${response.status})`)
  return (await response.json()) as CatalogResult
}

/** The full catalog entity (specs + copyable config snippet). */
export async function fetchCatalogEntity(catalogId: string): Promise<CatalogEntityDetail> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/hardware/catalog/${encodeURIComponent(catalogId)}`,
  )
  if (!response.ok) throw new Error(`Catalog entity request failed (${response.status})`)
  return (await response.json()) as CatalogEntityDetail
}
