import { resolveEndpoints } from '@/core/moonraker'

import type {
  BoardDiscovery,
  ConfigEdit,
  ConfigNode,
  FirmwareStatus,
  FlashPlan,
  FlashRequest,
  BeaconResponse,
  Device,
  DeviceSave,
  DevicesResponse,
  HealthReport,
  ProfilesResponse,
  ServicesResponse,
  TaskStatus,
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

/** Downloads a profile's built firmware binary (triggers a browser download). */
export async function downloadArtifact(profile: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/firmware/config/profiles/${encodeURIComponent(profile)}/artifact`,
  )
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Download failed (${response.status})`)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? `${profile}.bin`
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** Read-only: what a flash would do + its safety gates (runs nothing). */
export async function fetchFlashPlan(request: FlashRequest): Promise<FlashPlan> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/flash-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error(`Flash plan failed (${response.status})`)
  }
  return (await response.json()) as FlashPlan
}

/** Flashes a board, streaming the log via onChunk. Guarded server-side. */
export async function flashBoard(
  request: FlashRequest,
  onChunk: (text: string) => void,
): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/flash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok || !response.body) {
    throw new Error(`Flash request failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}

/** Fetches the saved devices (each device enriched with its last-flashed version). */
export async function fetchDevices(): Promise<DevicesResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/devices`)
  if (!response.ok) {
    throw new Error(`Devices request failed (${response.status})`)
  }
  return (await response.json()) as DevicesResponse
}

/** Adds or updates a board in the registry. Returns the saved device. */
export async function saveDevice(device: DeviceSave): Promise<Device> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/devices`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(device),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Save failed (${response.status})`)
  }
  return (await response.json()) as Device
}

/** Removes a board from the registry. */
export async function removeDevice(deviceId: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/firmware/devices?device_id=${encodeURIComponent(deviceId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    throw new Error(`Remove failed (${response.status})`)
  }
}

/** Binds a discovered bootloader identity (serial / dfu) to a device. */
export async function attachIdentity(
  deviceId: string,
  hardwareId: string,
  kind: string,
): Promise<Device> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/devices/attach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId, hardware_id: hardwareId, kind }),
  })
  if (!response.ok) {
    throw new Error(`Attach failed (${response.status})`)
  }
  return (await response.json()) as Device
}

/** Starts a background batch run (build-all / flash-all / …). Returns its task id. */
export async function startBatch(action: string): Promise<string> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!response.ok) {
    throw new Error(`Batch failed (${response.status})`)
  }
  return ((await response.json()) as { task_id: string }).task_id
}

/** Polls a batch task's log + status. */
export async function fetchTask(taskId: string): Promise<TaskStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/task/${encodeURIComponent(taskId)}`)
  if (!response.ok) {
    throw new Error(`Task status failed (${response.status})`)
  }
  return (await response.json()) as TaskStatus
}

/** Requests cancellation of a running batch task. */
export async function cancelTask(taskId: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  await fetch(`${backendUrl}/api/firmware/task/${encodeURIComponent(taskId)}/cancel`, {
    method: 'POST',
  })
}

/** Reports install-integrity health (sudoers, udev DFU rule, dfu-util). */
export async function fetchHealth(): Promise<HealthReport> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/health`)
  if (!response.ok) {
    throw new Error(`Health request failed (${response.status})`)
  }
  return (await response.json()) as HealthReport
}

/** Lists connected Beacon probes plus the plugin path and available version. */
export async function fetchBeacon(): Promise<BeaconResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/beacon`)
  if (!response.ok) {
    throw new Error(`Beacon request failed (${response.status})`)
  }
  return (await response.json()) as BeaconResponse
}

/** Updates a Beacon probe's firmware, streaming the log via onChunk. */
export async function flashBeacon(device: string, onChunk: (text: string) => void): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/beacon/flash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device }),
  })
  if (!response.ok || !response.body) {
    throw new Error(`Beacon flash failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}

/** Downloads a ZIP backup of the registry + profiles (triggers a browser download). */
export async function exportBackup(): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/backup/export`)
  if (!response.ok) {
    throw new Error(`Backup export failed (${response.status})`)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = 'filamind-backup.zip'
  link.click()
  URL.revokeObjectURL(url)
}

/** Restores a backup ZIP (raw bytes). Returns what was put back. */
export async function importBackup(
  file: File,
): Promise<{ restored_devices: boolean; restored_profiles: string[] }> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/backup/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: await file.arrayBuffer(),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Import failed (${response.status})`)
  }
  return (await response.json()) as { restored_devices: boolean; restored_profiles: string[] }
}

/** Lists the host's Klipper / Moonraker services and their active state. */
export async function fetchServices(): Promise<ServicesResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/services`)
  if (!response.ok) {
    throw new Error(`Services request failed (${response.status})`)
  }
  return (await response.json()) as ServicesResponse
}

/** Starts / stops / restarts every Klipper / Moonraker service. */
export async function manageServices(action: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/firmware/services/${encodeURIComponent(action)}`,
    { method: 'POST' },
  )
  if (!response.ok) {
    throw new Error(`Service ${action} failed (${response.status})`)
  }
}

/** Reboots a board into a bootloader (Katapult or DFU), streaming via onChunk. */
export async function rebootBoard(
  request: { method: string; device: string; interface: string; mode?: string },
  onChunk: (text: string) => void,
): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/firmware/reboot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok || !response.body) {
    throw new Error(`Reboot failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}
