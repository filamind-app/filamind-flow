import { resolveEndpoints } from '@/core/moonraker'

import type {
  LiveMacrosResult,
  MachineLimits,
  MachineLimitsResult,
  MacroDef,
  SimResult,
} from './types'

/** Simulate a literal G-code program (pure compute on the server; no printer). Optional macro
 *  ``params`` substitute its ``{ params.X }`` expressions; ``limits`` enable bounds/speed checks. */
export async function simulateGcode(
  gcode: string,
  params: Record<string, string> = {},
  limits: MachineLimits | null = null,
): Promise<SimResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/macro/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gcode, params, limits }),
  })
  if (!response.ok) throw new Error(`Simulate failed (${response.status})`)
  return (await response.json()) as SimResult
}

/** The printer's real build envelope + speed cap, to ground the simulation (null if unreachable). */
export async function fetchLimits(): Promise<MachineLimitsResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/macro/limits`)
  if (!response.ok) throw new Error(`Limits request failed (${response.status})`)
  return (await response.json()) as MachineLimitsResult
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
