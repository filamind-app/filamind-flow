/** Pure builder for the axes-map velocity-sequence chart: the three per-axis strokes
 *  laid side by side, each with its integrated vx/vy/vz curves on a shared scale, so
 *  you can see which accelerometer axis responded to each machine move. Dependency-free
 *  SVG, same approach as chart.ts / compare.ts.
 */

import type { VelocitySeries } from './types'

export interface AxesZone {
  x0: number
  x1: number
  centerX: number
  /** Machine axis moved in this zone (X/Y/Z). */
  axis: string
  /** Accelerometer axis it landed on, e.g. "+z". */
  detected: string
  confidence: number
  extrapolated: boolean
  /** SVG polyline points for each accel-axis velocity curve. */
  vx: string
  vy: string
  vz: string
}

export interface AxesVelocityChart {
  width: number
  height: number
  zones: AxesZone[]
  /** x of each inter-zone divider. */
  boundaries: number[]
  zeroY: number
  colors: { x: string; y: string; z: string }
}

const COLORS = { x: '#ff5247', y: '#5b8cff', z: '#00e0c6' }

/** Builds the SVG model (empty zones if there's no data). */
export function buildAxesVelocityChart(
  series: VelocitySeries[],
  width = 320,
  height = 150,
): AxesVelocityChart {
  const pad = { l: 4, r: 4, t: 8, b: 14 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const zeroY = pad.t + innerH / 2
  if (!series.length) {
    return { width, height, zones: [], boundaries: [], zeroY, colors: COLORS }
  }

  let vmax = 1e-6
  for (const s of series) {
    for (const arr of [s.vx, s.vy, s.vz]) {
      for (const v of arr) vmax = Math.max(vmax, Math.abs(v))
    }
  }

  const zoneW = innerW / series.length
  const yAt = (v: number): number => zeroY - (v / vmax) * (innerH / 2)
  const zones: AxesZone[] = []
  const boundaries: number[] = []

  series.forEach((s, i) => {
    const x0 = pad.l + i * zoneW
    if (i > 0) boundaries.push(x0)
    const n = s.t.length
    const span = n > 1 ? s.t[n - 1] - s.t[0] : 1
    const xAt = (k: number): number => x0 + (span > 0 ? ((s.t[k] - s.t[0]) / span) * zoneW : 0)
    const poly = (arr: number[]): string =>
      arr.map((v, k) => `${xAt(k).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
    zones.push({
      x0,
      x1: x0 + zoneW,
      centerX: x0 + zoneW / 2,
      axis: s.axis.toUpperCase(),
      detected: s.detected_axis,
      confidence: s.confidence,
      extrapolated: s.extrapolated,
      vx: poly(s.vx),
      vy: poly(s.vy),
      vz: poly(s.vz),
    })
  })

  return { width, height, zones, boundaries, zeroY, colors: COLORS }
}
