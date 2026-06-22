import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { Rule, RulesView } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

export async function getRules(): Promise<RulesView> {
  const r = await fetch(`${base()}/api/rules`)
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function setEngine(enabled: boolean): Promise<void> {
  const r = await fetch(`${base()}/api/rules/engine`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new Error(httpError(r.status))
}

export async function upsertRule(rule: Rule): Promise<Rule> {
  const r = await fetch(`${base()}/api/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rule),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function deleteRule(id: string): Promise<void> {
  const r = await fetch(`${base()}/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(httpError(r.status))
}
