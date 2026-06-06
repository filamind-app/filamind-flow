import { resolveEndpoints } from '@/core/moonraker'

import type { ConfigFileList, ConfigFileView, ConfigSaveResult } from './types'

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
