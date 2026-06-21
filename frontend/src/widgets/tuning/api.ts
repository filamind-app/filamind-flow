import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { ApplyResult, TempTowerParams, TempTowerPlan, TowerParams, TowerPlan } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json() as Promise<T>
}

export function planPa(params: TowerParams): Promise<TowerPlan> {
  return postJson('/api/tuning/pa/plan', params)
}

export function applyPa(value: number): Promise<ApplyResult> {
  return postJson('/api/tuning/pa/apply', { value })
}

export function planRetraction(params: TowerParams): Promise<TowerPlan> {
  return postJson('/api/tuning/retraction/plan', params)
}

export function applyRetraction(value: number): Promise<ApplyResult> {
  return postJson('/api/tuning/retraction/apply', { value })
}

export function planTemp(params: TempTowerParams): Promise<TempTowerPlan> {
  return postJson('/api/tuning/temp/plan', params)
}

export function applyTemp(heater: string, value: number): Promise<ApplyResult> {
  return postJson('/api/tuning/temp/apply', { heater, value })
}
