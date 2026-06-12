import { resolveEndpoints } from '@/core/moonraker'

import type {
  ArchiveListResponse,
  ArchiveRun,
  AxesMapResult,
  BeltComparison,
  NoiseResult,
  ResonanceFilesResponse,
  ShaperAnalysis,
  StaticExcitationResult,
  VibrationsProfile,
} from './types'

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
export async function analyzeResonanceFile(
  path: string,
  opts: AnalyzeOptions = {},
): Promise<ShaperAnalysis> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams({ path })
  if (opts.axis) params.set('axis', opts.axis)
  if (opts.scv != null) params.set('scv', String(opts.scv))
  if (opts.maxFreq != null) params.set('max_freq', String(opts.maxFreq))
  if (opts.maxSmoothing != null) params.set('max_smoothing', String(opts.maxSmoothing))
  if (opts.dampingRatio != null) params.set('damping_ratio', String(opts.dampingRatio))
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

/** Runs a resonance test on each CoreXY belt diagonal (moves the toolhead). */
export async function compareBelts(): Promise<BeltComparison> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/compare-belts`, { method: 'POST' })
  if (!response.ok) throw new Error(await errorDetail(response, 'Belt comparison failed'))
  return (await response.json()) as BeltComparison
}

/** Detects the accelerometer's axes_map by jogging the toolhead +X/+Y/+Z. */
export async function runAxesMap(): Promise<AxesMapResult> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/axes-map`, { method: 'POST' })
  if (!response.ok) throw new Error(await errorDetail(response, 'Axes-map detection failed'))
  return (await response.json()) as AxesMapResult
}

/** Holds an axis vibrating near `freq` for `duration` s (moves the toolhead). */
export async function runStaticExcitation(
  axis: string,
  freq: number,
  duration: number,
): Promise<StaticExcitationResult> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams({
    axis,
    freq: String(freq),
    duration: String(duration),
  })
  const response = await fetch(`${backendUrl}/api/shaper/excitate?${params}`, { method: 'POST' })
  if (!response.ok) throw new Error(await errorDetail(response, 'Sustain-frequency test failed'))
  return (await response.json()) as StaticExcitationResult
}

/** Tuning knobs for a vibrations profile (all optional; backend supplies defaults). */
export interface VibrationsOptions {
  /** Top speed to test, mm/s. */
  maxSpeed?: number
  /** Lowest speed to test, mm/s. */
  minSpeed?: number
  /** Speed step, mm/s (finer = longer run). */
  speedIncrement?: number
  /** Movement size, mm. */
  size?: number
  /** Acceleration during the sweep, mm/s². */
  accel?: number
}

/** Sweeps speed × motor-angle and profiles machine vibrations (moves the toolhead for minutes).
 *  Runs SUPERVISED: a background task with polled progress, cancel, and a server-held result —
 *  same signature and result shape as the old blocking call (see supervised.ts). */
export async function runVibrationsProfile(
  opts: VibrationsOptions = {},
): Promise<VibrationsProfile> {
  const { runSupervisedVibrations } = await import('./supervised')
  return runSupervisedVibrations(opts)
}

/** Lists the saved runs (captures + generated configs) in the on-host archive. */
export async function listArchive(): Promise<ArchiveListResponse> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/archive`)
  if (!response.ok) throw new Error(await errorDetail(response, 'Listing the archive failed'))
  return (await response.json()) as ArchiveListResponse
}

/** Deletes an archived run (folder + index entry). */
export async function deleteArchiveRun(id: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/archive/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(await errorDetail(response, 'Delete failed'))
}

/** Downloads a file (CSV / config) stored in an archived run (browser download). */
export async function downloadArchiveFile(id: string, filename: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(
    `${backendUrl}/api/shaper/archive/${encodeURIComponent(id)}/file/${encodeURIComponent(filename)}`,
  )
  if (!response.ok) throw new Error(await errorDetail(response, 'Download failed'))
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** Saves a generated `[input_shaper]` config to the archive (new run, or attached). */
export async function saveConfigToArchive(
  configText: string,
  axis?: string | null,
  summary: Record<string, unknown> = {},
): Promise<ArchiveRun> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/shaper/archive/save-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_text: configText, axis: axis ?? null, summary }),
  })
  if (!response.ok) throw new Error(await errorDetail(response, 'Save to archive failed'))
  return (await response.json()) as ArchiveRun
}

/** Copies an existing host resonance CSV into the archive as a saved run. */
export async function saveFileToArchive(
  path: string,
  kind = 'shaper',
  axis?: string | null,
): Promise<ArchiveRun> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams({ path, kind })
  if (axis) params.set('axis', axis)
  const response = await fetch(`${backendUrl}/api/shaper/archive/save-file?${params}`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await errorDetail(response, 'Save to archive failed'))
  return (await response.json()) as ArchiveRun
}
