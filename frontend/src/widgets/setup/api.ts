import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { SetupActionResult, SetupCatalog, SetupStatus } from './types'

function base(): string {
  return resolveEndpoints().backendUrl
}

/** A setup-action error carrying the HTTP status so the UI can tell refused (403) from other faults. */
export class SetupActionError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'SetupActionError'
  }
}

/** The component catalog (groups → components). */
export async function fetchCatalog(): Promise<SetupCatalog> {
  const r = await fetch(`${base()}/api/setup/catalog`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupCatalog
}

/** Installed status per component + whether GUI writes are enabled on this host. */
export async function fetchStatus(): Promise<SetupStatus> {
  const r = await fetch(`${base()}/api/setup/status`)
  if (!r.ok) throw new Error(httpError(r.status))
  return (await r.json()) as SetupStatus
}

async function post(path: string, body: unknown): Promise<SetupActionResult> {
  const r = await fetch(`${base()}/api/setup/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await r.json().catch(() => ({}))) as { detail?: string } & SetupActionResult
  if (!r.ok) throw new SetupActionError(data.detail || httpError(r.status), r.status)
  return data
}

export const installComponent = (id: string): Promise<SetupActionResult> => post('install', { id })
export const updateComponent = (id: string): Promise<SetupActionResult> => post('update', { id })
export const removeComponent = (id: string, confirm: string): Promise<SetupActionResult> =>
  post('remove', { id, confirm })
export const setPort = (id: string, port: number): Promise<SetupActionResult> =>
  post('port', { id, port })
