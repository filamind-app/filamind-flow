import { resolveEndpoints } from '@/core/moonraker'

import type {
  ConfigDriftResult,
  ConfigFileList,
  ConfigFileView,
  ConfigSaveResult,
  FieldPolicyResponse,
  PinDoctorResult,
  PinMapResult,
} from './types'

/** An Error that carries the HTTP status, so callers can special-case 409 (printer busy). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function errorFrom(response: Response, fallback: string): Promise<ApiError> {
  let detail = fallback
  try {
    const body = (await response.json()) as { detail?: string }
    if (body?.detail) detail = body.detail
  } catch {
    // non-JSON error body — keep the fallback
  }
  return new ApiError(detail, response.status)
}

/** List the editable config files (`.cfg` / `.conf`) under Moonraker's `config` root. */
export async function fetchConfigFiles(): Promise<ConfigFileList> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/files`)
  if (!response.ok) {
    throw new Error(`Config file list request failed (${response.status})`)
  }
  return (await response.json()) as ConfigFileList
}

/** Fetch and parse one config file into the structured editor view (sections + issues). */
export async function fetchConfigFile(filename: string): Promise<ConfigFileView> {
  const { backendUrl } = resolveEndpoints()
  const url = `${backendUrl}/api/config/file?filename=${encodeURIComponent(filename)}`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Config file request failed (${response.status})`)
  }
  return (await response.json()) as ConfigFileView
}

/** Compare the on-disk file to the live running config (drift + pending SAVE_CONFIG + warnings). */
export async function fetchConfigDrift(filename: string): Promise<ConfigDriftResult> {
  const { backendUrl } = resolveEndpoints()
  const url = `${backendUrl}/api/config/drift?filename=${encodeURIComponent(filename)}`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Drift request failed (${response.status})`)
  }
  return (await response.json()) as ConfigDriftResult
}

/** The editable-register policy for one TMC model (control + range per field). */
export async function fetchFieldPolicy(model: string): Promise<FieldPolicyResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/drivers/field-policy/${encodeURIComponent(model)}`,
  )
  if (!response.ok) {
    throw new Error(`Field policy request failed (${response.status})`)
  }
  return (await response.json()) as FieldPolicyResponse
}

/** A whole-config pin-conflict scan (every MCU): double-assigned pins + electronics caveats. */
export async function fetchPinDoctor(): Promise<PinDoctorResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/pin-doctor`)
  if (!response.ok) {
    throw new Error(`Pin doctor request failed (${response.status})`)
  }
  return (await response.json()) as PinDoctorResult
}

/** Per-MCU board pins (name + owners + caveat) for pin-aware `*_pin` editing. */
export async function fetchPinMap(): Promise<PinMapResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/pin-map`)
  if (!response.ok) {
    throw new Error(`Pin map request failed (${response.status})`)
  }
  return (await response.json()) as PinMapResult
}

/** Set one param to its live value via the round-trip engine; returns the new file text (no write). */
export async function adoptParam(
  content: string,
  section: string,
  key: string,
  value: string,
): Promise<string> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/adopt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, section, key, value }),
  })
  if (!response.ok) {
    throw new Error(`Adopt failed (${response.status})`)
  }
  return ((await response.json()) as { content: string }).content
}

/** Back up then overwrite one config file. Throws {@link ApiError} (status 409 = printer busy). */
export async function saveConfigFile(filename: string, content: string): Promise<ConfigSaveResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content }),
  })
  if (!response.ok) {
    throw await errorFrom(response, `Save failed (${response.status})`)
  }
  return (await response.json()) as ConfigSaveResult
}

/** Trigger FIRMWARE_RESTART to apply a saved config. Throws {@link ApiError} (409 = busy). */
export async function restartFirmware(): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/config/restart`, { method: 'POST' })
  if (!response.ok) {
    throw await errorFrom(response, `Restart failed (${response.status})`)
  }
}
