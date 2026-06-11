import { resolveEndpoints } from '@/core/moonraker'

import type { LiveMacrosResult, MacroDef, SimResult } from './types'

/** Simulate a literal G-code program (pure compute on the server; no printer). Optional macro
 *  ``params`` substitute its ``{ params.X }`` expressions. */
export async function simulateGcode(
  gcode: string,
  params: Record<string, string> = {},
): Promise<SimResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/macro/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gcode, params }),
  })
  if (!response.ok) throw new Error(`Simulate failed (${response.status})`)
  return (await response.json()) as SimResult
}

/** The printer's OWN installed [gcode_macro] definitions, to load + simulate (empty if unreachable). */
export async function fetchLiveMacros(): Promise<LiveMacrosResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/macro/live`)
  if (!response.ok) throw new Error(`Live macros request failed (${response.status})`)
  return (await response.json()) as LiveMacrosResult
}

/** The built-in macro reference library. */
export async function fetchMacros(): Promise<MacroDef[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/reference/macros`)
  if (!response.ok) throw new Error(`Macro library request failed (${response.status})`)
  return (await response.json()) as MacroDef[]
}
