import { httpError } from '@/core/describeError'
import { resolveEndpoints } from '@/core/moonraker'

import type { ConfigTemplate } from './types'

/** The curated insertable config / macro templates. */
export async function fetchTemplates(): Promise<ConfigTemplate[]> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/reference/templates`)
  if (!response.ok) throw new Error(httpError(response.status))
  return (await response.json()) as ConfigTemplate[]
}
