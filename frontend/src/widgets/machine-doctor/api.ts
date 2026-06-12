import { resolveEndpoints } from '@/core/moonraker'

import type { DoctorReport } from './types'

/** Run the full read-only scan and return the graded report. */
export async function fetchDoctorScan(): Promise<DoctorReport> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/doctor/scan`)
  if (!response.ok) throw new Error(`Doctor scan failed (${response.status})`)
  return (await response.json()) as DoctorReport
}
