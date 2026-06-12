import { resolveEndpoints } from '@/core/moonraker'

import type { HotendRow, MaxFlowParams, MaxFlowPlan, MaxFlowResult } from './types'

/** An Error carrying the HTTP status, so callers can special-case 409 (printer busy). */
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

/** The reference hotend table (melt-zone / expected flow / suggested temp). */
export async function fetchHotends(): Promise<HotendRow[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/reference/hotends`)
  if (!response.ok) throw new Error(`Hotend table request failed (${response.status})`)
  return (await response.json()) as HotendRow[]
}

/** Dry-run preview of the flow ramp (pure compute on the server; no actuation). */
export async function planMaxFlow(params: MaxFlowParams): Promise<MaxFlowPlan> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/maxflow/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!response.ok) throw await errorFrom(response, `Plan failed (${response.status})`)
  return (await response.json()) as MaxFlowPlan
}

/** Run the live max-flow test (ACTUATING: heat + extrude + sample) as a SUPERVISED background
 *  task: polled per-step progress, cancel (the heater is always cut), a server-held result, and
 *  reattach-after-reload. Same result shape as the old blocking call. */
export async function runMaxFlow(params: MaxFlowParams): Promise<MaxFlowResult> {
  const { runSupervisedMaxFlow } = await import('./supervised')
  return runSupervisedMaxFlow(params)
}

/** Start the supervised run; returns the task id (used by supervised.ts). */
export async function startMaxFlowTask(params: MaxFlowParams): Promise<string> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/maxflow/run/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!response.ok) throw await errorFrom(response, `Run failed to start (${response.status})`)
  return ((await response.json()) as { task_id: string }).task_id
}
