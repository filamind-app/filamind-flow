import { resolveEndpoints } from '@/core/moonraker'

import type { ConfigFileList, ConfigFileView } from './types'

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
