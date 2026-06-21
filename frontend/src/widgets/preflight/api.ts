import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { PreflightResult } from './types'

export async function getPreflight(): Promise<PreflightResult> {
  const r = await fetch(`${resolveEndpoints().backendUrl}/api/preflight`)
  if (!r.ok) throw new Error(httpError(r.status))
  return r.json()
}
