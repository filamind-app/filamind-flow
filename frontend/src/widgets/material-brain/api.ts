import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { MaterialFlowCheck, MaterialProfile } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

export async function listMaterials(): Promise<MaterialProfile[]> {
  const r = await fetch(`${base()}/api/material`)
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function saveMaterial(
  profile: MaterialProfile,
  oldId?: string,
): Promise<MaterialProfile> {
  const q = oldId ? `?old_id=${encodeURIComponent(oldId)}` : ''
  const r = await fetch(`${base()}/api/material${q}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function deleteMaterial(id: string): Promise<void> {
  const r = await fetch(`${base()}/api/material/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(httpError(r.status))
}

export async function flowCheck(id: string, hotend?: string): Promise<MaterialFlowCheck> {
  const q = hotend ? `?hotend=${encodeURIComponent(hotend)}` : ''
  const r = await fetch(`${base()}/api/material/${encodeURIComponent(id)}/flow-check${q}`)
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}
