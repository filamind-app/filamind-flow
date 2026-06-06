import { resolveEndpoints } from '@/core/moonraker'

import type { MacroDef, SimResult } from './types'

/** Simulate a literal G-code program (pure compute on the server; no printer). */
export async function simulateGcode(gcode: string): Promise<SimResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/macro/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gcode }),
  })
  if (!response.ok) throw new Error(`Simulate failed (${response.status})`)
  return (await response.json()) as SimResult
}

/** The built-in macro reference library. */
export async function fetchMacros(): Promise<MacroDef[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/reference/macros`)
  if (!response.ok) throw new Error(`Macro library request failed (${response.status})`)
  return (await response.json()) as MacroDef[]
}
