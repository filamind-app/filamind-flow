/** Pure builder for the frequency-response chart — maps an analysis's data
 *  series onto SVG polyline coordinates so the widget can draw them with no
 *  charting dependency. Two y-axes (like Klipper's calibrate_shaper plot): the
 *  PSD curves scale to the peak power, the shaper curves to the 0..1 reduction
 *  ratio. Everything shares the frequency x-axis.
 */

import { median, peakIndex } from './signal'
import type { ShaperAnalysis } from './types'

export interface PlotSeries {
  name: string
  color: string
  /** Dashed for non-recommended shaper curves. */
  dashed: boolean
  /** SVG polyline `points` attribute, e.g. "0,10 5,8 …". */
  points: string
}

/** The dominant PSD peak, marked on the plot. */
export interface PeakMarker {
  x: number
  y: number
  freq: number
  /** Pre-formatted label, e.g. "57 Hz". */
  label: string
}

export interface ResponseChart {
  width: number
  height: number
  /** Power-spectral-density curves (X+Y+Z, X, Y, Z), left axis. */
  psd: PlotSeries[]
  /** Per-shaper vibration-reduction curves (0..1), right axis. */
  shapers: PlotSeries[]
  /** Frequency gridline labels along the x-axis. */
  xTicks: { x: number; label: string }[]
  /** Dominant resonance peak, for annotation (null with no data). */
  peak: PeakMarker | null
  /** y of the PSD noise floor (median power), for a faint reference line. */
  noiseY: number | null
}

const PSD_COLORS: Record<string, string> = {
  sum: '#111111', // ink — the X+Y+Z total
  x: '#ff5247', // brand-red
  y: '#5b8cff', // brand-blue
  z: '#00e0c6', // brand-cyan
}

/** Builds the SVG model for a resonance analysis (empty series if no data). */
export function buildResponseChart(
  analysis: ShaperAnalysis,
  width = 320,
  height = 150,
): ResponseChart {
  const pad = { l: 4, r: 4, t: 6, b: 12 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const freqs = analysis.freqs
  const n = freqs.length
  if (!n) return { width, height, psd: [], shapers: [], xTicks: [], peak: null, noiseY: null }

  const fMax = freqs[n - 1] || 1
  const psdMax = Math.max(1e-12, ...analysis.psd_sum)
  const xAt = (f: number): number => pad.l + (f / fMax) * innerW
  const yPsd = (v: number): number => pad.t + innerH - (v / psdMax) * innerH
  const yRatio = (v: number): number => pad.t + innerH - Math.min(1, v) * innerH

  const poly = (values: number[], y: (v: number) => number): string =>
    values.map((v, i) => `${xAt(freqs[i]).toFixed(1)},${y(v).toFixed(1)}`).join(' ')

  const psd: PlotSeries[] = [
    { name: 'X+Y+Z', color: PSD_COLORS.sum, dashed: false, points: poly(analysis.psd_sum, yPsd) },
    { name: 'X', color: PSD_COLORS.x, dashed: false, points: poly(analysis.psd_x, yPsd) },
    { name: 'Y', color: PSD_COLORS.y, dashed: false, points: poly(analysis.psd_y, yPsd) },
    { name: 'Z', color: PSD_COLORS.z, dashed: false, points: poly(analysis.psd_z, yPsd) },
  ]

  const shapers: PlotSeries[] = analysis.shaper_curves.map((c) => ({
    name: c.name,
    color: c.name === analysis.recommended_shaper ? '#ff5c8a' : '#6c7086',
    dashed: c.name !== analysis.recommended_shaper,
    points: poly(c.vals, yRatio),
  }))

  const xTicks: { x: number; label: string }[] = []
  for (let f = 0; f <= fMax; f += 50) xTicks.push({ x: xAt(f), label: String(f) })

  // Annotate the dominant resonance and the noise floor.
  const pi = peakIndex(analysis.psd_sum)
  const peak: PeakMarker | null =
    pi >= 0
      ? {
          x: xAt(freqs[pi]),
          y: yPsd(analysis.psd_sum[pi]),
          freq: freqs[pi],
          label: `${freqs[pi].toFixed(0)} Hz`,
        }
      : null
  const noiseY = analysis.psd_sum.length ? yPsd(median(analysis.psd_sum)) : null

  return { width, height, psd, shapers, xTicks, peak, noiseY }
}
