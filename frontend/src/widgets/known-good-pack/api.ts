import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { KgpDetail, KgpPack, KgpRestoreResult } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

export async function listPacks(): Promise<KgpPack[]> {
  const r = await fetch(`${base()}/api/kgp`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()).packs as KgpPack[]
}

export async function createPack(label: string): Promise<KgpPack> {
  const r = await fetch(`${base()}/api/kgp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function packDetail(id: string): Promise<KgpDetail> {
  const r = await fetch(`${base()}/api/kgp/${encodeURIComponent(id)}`)
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function restorePack(id: string): Promise<KgpRestoreResult> {
  const r = await fetch(`${base()}/api/kgp/${encodeURIComponent(id)}/restore`, { method: 'POST' })
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}

export async function deletePack(id: string): Promise<void> {
  const r = await fetch(`${base()}/api/kgp/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(httpError(r.status))
}
