import { resolveEndpoints } from '@/core/moonraker'

import type { ShaperAnalysis } from './types'

/** Tuning knobs for an analysis (all optional; the backend supplies defaults). */
export interface AnalyzeOptions {
  /** Axis this CSV belongs to (x / y); omit to leave it unlabelled. */
  axis?: string
  /** Square corner velocity, mm/s. */
  scv?: number
  /** Maximum frequency to analyse, Hz. */
  maxFreq?: number
  /** Cap on shaper smoothing. */
  maxSmoothing?: number
  /** Override the damping ratio. */
  dampingRatio?: number
}

/** Uploads a resonance CSV and returns the recommended shaper + plot data. */
export async function analyzeResonance(
  file: File,
  opts: AnalyzeOptions = {},
): Promise<ShaperAnalysis> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams()
  if (opts.axis) params.set('axis', opts.axis)
  if (opts.scv != null) params.set('scv', String(opts.scv))
  if (opts.maxFreq != null) params.set('max_freq', String(opts.maxFreq))
  if (opts.maxSmoothing != null) params.set('max_smoothing', String(opts.maxSmoothing))
  if (opts.dampingRatio != null) params.set('damping_ratio', String(opts.dampingRatio))
  const query = params.toString()

  const response = await fetch(`${backendUrl}/api/shaper/analyze${query ? `?${query}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/csv' },
    body: file,
  })
  if (!response.ok) {
    let detail = `Analysis failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* non-JSON error body — keep the status message */
    }
    throw new Error(detail)
  }
  return (await response.json()) as ShaperAnalysis
}
