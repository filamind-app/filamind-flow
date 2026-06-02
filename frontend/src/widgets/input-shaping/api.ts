import { resolveEndpoints } from '@/core/moonraker'

import type { NoiseResult, ResonanceFilesResponse, ShaperAnalysis } from './types'

/** Extracts a backend error detail, falling back to the status line. */
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string }
    if (body.detail) return body.detail
  } catch {
    /* non-JSON body */
  }
  return `${fallback} (${response.status})`
}

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

/** Lists the resonance CSVs Klipper has written on the printer host. */
export async function listResonanceFiles(): Promise<ResonanceFilesResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/files`)
  if (!response.ok) throw new Error(await errorDetail(response, 'Listing printer files failed'))
  return (await response.json()) as ResonanceFilesResponse
}

/** Analyses a resonance CSV that already exists on the printer host (by path). */
export async function analyzeResonanceFile(path: string, axis?: string): Promise<ShaperAnalysis> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams({ path })
  if (axis) params.set('axis', axis)
  const response = await fetch(`${backendUrl}/api/shaper/analyze-file?${params}`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await errorDetail(response, 'Analysis failed'))
  return (await response.json()) as ShaperAnalysis
}

/** Runs a live TEST_RESONANCES on the printer (moves the toolhead) and analyses it. */
export async function runLiveTest(axis: string): Promise<ShaperAnalysis> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/live-test?axis=${axis}`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await errorDetail(response, 'Live test failed'))
  return (await response.json()) as ShaperAnalysis
}

/** Runs MEASURE_AXES_NOISE (motion-free) to check the accelerometer mount. */
export async function measureNoise(): Promise<NoiseResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/noise`, { method: 'POST' })
  if (!response.ok) throw new Error(await errorDetail(response, 'Noise check failed'))
  return (await response.json()) as NoiseResult
}
