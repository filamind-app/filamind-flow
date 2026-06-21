import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { PaApplyResult, PaTowerParams, PaTowerPlan } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

export async function planPa(params: PaTowerParams): Promise<PaTowerPlan> {
  const r = await fetch(`${base()}/api/tuning/pa/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function applyPa(value: number): Promise<PaApplyResult> {
  const r = await fetch(`${base()}/api/tuning/pa/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}
