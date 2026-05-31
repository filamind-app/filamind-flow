import { resolveEndpoints } from '@/core/moonraker'

import type {
  BoardDiscovery,
  ConfigEdit,
  ConfigNode,
  FirmwareStatus,
  ProfilesResponse,
} from './types'

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

interface ConfigTreeBody {
  profile?: string | null
  values: ConfigEdit[]
  show_optional?: boolean
}

/** Loads Klipper's Kconfig menu tree, with an optional base profile + live edits. */
export async function fetchConfigTree(body: ConfigTreeBody): Promise<ConfigNode[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/config/tree`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Config tree request failed (${response.status})`)
  }
  return (await response.json()) as ConfigNode[]
}

/** Lists saved per-board firmware profiles. */
export async function fetchProfiles(): Promise<ProfilesResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/config/profiles`)
  if (!response.ok) {
    throw new Error(`Profiles request failed (${response.status})`)
  }
  return (await response.json()) as ProfilesResponse
}

/** Saves Kconfig edits (atop an optional base) as a named profile. */
export async function saveProfile(body: {
  name: string
  values: ConfigEdit[]
  base_profile?: string | null
}): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/config/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Save failed (${response.status})`)
  }
}

/** Deletes a saved firmware profile. */
export async function deleteProfile(name: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/firmware/config/profiles/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    throw new Error(`Delete failed (${response.status})`)
  }
}

/** Streams a profile's firmware build log, invoking onChunk for each chunk. */
export async function buildFirmware(
  profile: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/build/${encodeURIComponent(profile)}`)
  if (!response.ok || !response.body) {
    throw new Error(`Build request failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}
