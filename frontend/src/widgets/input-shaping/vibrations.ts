/** Pure builders for the machine vibrations profile: a speed-vs-energy line chart
 *  (with the resonance peaks to avoid + the smoothest bands marked), a polar plot of
 *  vibration energy by travel direction, and an angle×speed heatmap. Dependency-free
 *  SVG; the heatmap reuses the brand power→colour ramp from the spectrogram view.
 */

import { ramp } from './spectrogram-chart'
import type { VibrationsProfile } from './types'

export interface SpeedBand {
  x: number
  w: number
}
export interface AxisTick {
  x: number
  label: string
}

export interface SpeedProfileChart {
  width: number
  height: number
  /** The vibration metric polyline (the main curve). */
  energyPoints: string
  /** The max-energy polyline (faint reference). */
  maxPoints: string
  /** Smoothest-speed bands (lime). */
  bands: SpeedBand[]
  /** Resonance peaks to avoid (red guide lines). */
  peaks: { x: number }[]
  /** The recommended smooth speed (cyan guide), null if none. */
  recommendedX: number | null
  speedTicks: AxisTick[]
}

export interface PolarSpoke {
  x: number
  y: number
  label: string
}
export interface PolarChart {
  size: number
  cx: number
  cy: number
  /** Outer grid radius. */
  gridR: number
  /** The energy polygon (points string), radius scaled by per-angle energy. */
  polygon: string
  /** Spokes at the measured motor angles. */
  spokes: PolarSpoke[]
}

export interface HeatCell {
  x: number
  y: number
  w: number
  h: number
  fill: string
}
export interface VibHeatmap {
  width: number
  height: number
  cells: HeatCell[]
  speedTicks: AxisTick[]
  angleTicks: { y: number; label: string }[]
}

/** Speed (x) vs normalised vibration energy (y), with peaks + smooth bands marked. */
export function buildSpeedProfile(
  profile: VibrationsProfile,
  width = 320,
  height = 130,
): SpeedProfileChart {
  const pad = { l: 6, r: 6, t: 8, b: 14 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const { speeds, energy_profile, max_profile } = profile
  if (speeds.length < 2) {
    return {
      width,
      height,
      energyPoints: '',
      maxPoints: '',
      bands: [],
      peaks: [],
      recommendedX: null,
      speedTicks: [],
    }
  }
  const sMin = speeds[0]
  const sMax = speeds[speeds.length - 1]
  const span = sMax - sMin || 1
  const xAt = (speed: number): number => pad.l + ((speed - sMin) / span) * innerW
  const yAt = (v: number): number => pad.t + innerH - Math.max(0, Math.min(1, v)) * innerH
  const line = (vals: number[]): string =>
    vals.map((v, i) => `${xAt(speeds[i]).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')

  const bands: SpeedBand[] = profile.good_speed_ranges.map((r) => {
    const x = xAt(Math.max(sMin, r.start))
    const w = Math.max(1.5, xAt(Math.min(sMax, r.end)) - x)
    return { x, w }
  })
  const peaks = profile.peak_speeds
    .filter((p) => p >= sMin && p <= sMax)
    .map((p) => ({ x: xAt(p) }))
  const recommendedX =
    profile.recommended_speed != null &&
    profile.recommended_speed >= sMin &&
    profile.recommended_speed <= sMax
      ? xAt(profile.recommended_speed)
      : null

  const speedTicks: AxisTick[] = []
  const tickStep = span > 250 ? 100 : 50
  for (let s = Math.ceil(sMin / tickStep) * tickStep; s <= sMax; s += tickStep) {
    speedTicks.push({ x: xAt(s), label: String(s) })
  }

  return {
    width,
    height,
    energyPoints: line(energy_profile),
    maxPoints: max_profile.length === speeds.length ? line(max_profile) : '',
    bands: bands.map((b) => ({ x: b.x, w: b.w })),
    peaks,
    recommendedX,
    speedTicks,
  }
}

/** Vibration energy by travel direction (0° = +X, CCW). A closed polar polygon. */
export function buildPolarAngles(profile: VibrationsProfile, size = 150): PolarChart {
  const cx = size / 2
  const cy = size / 2
  const gridR = size / 2 - 14
  const { angles, angle_energy } = profile
  const minR = gridR * 0.12 // keep a small core so near-zero directions stay visible
  const pts: string[] = []
  for (let i = 0; i < angles.length; i++) {
    const theta = (angles[i] * Math.PI) / 180
    const r = minR + (gridR - minR) * Math.max(0, Math.min(1, angle_energy[i] ?? 0))
    const x = cx + r * Math.cos(theta)
    const y = cy - r * Math.sin(theta)
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`)
  }
  const spokes: PolarSpoke[] = profile.main_angles.map((a) => {
    const theta = (a * Math.PI) / 180
    return {
      x: cx + gridR * Math.cos(theta),
      y: cy - gridR * Math.sin(theta),
      label: `${a.toFixed(0)}°`,
    }
  })
  return { size, cx, cy, gridR, polygon: pts.join(' '), spokes }
}

/** Angle (rows, y) × speed (cols, x) heatmap of directional vibration energy. */
export function buildVibHeatmap(profile: VibrationsProfile, width = 320, height = 150): VibHeatmap {
  const pad = { l: 6, r: 6, t: 6, b: 14 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const { speeds, angles, spectrogram } = profile
  if (!speeds.length || !angles.length) {
    return { width, height, cells: [], speedTicks: [], angleTicks: [] }
  }
  const cellW = innerW / speeds.length
  const cellH = innerH / angles.length
  const cells: HeatCell[] = []
  for (let ai = 0; ai < angles.length; ai++) {
    const row = spectrogram[ai] ?? []
    for (let si = 0; si < speeds.length; si++) {
      cells.push({
        x: pad.l + si * cellW,
        y: pad.t + ai * cellH,
        w: cellW + 0.6,
        h: cellH + 0.6,
        fill: ramp(row[si] ?? 0),
      })
    }
  }
  const sMin = speeds[0]
  const sMax = speeds[speeds.length - 1]
  const span = sMax - sMin || 1
  const speedTicks: AxisTick[] = []
  const tickStep = span > 250 ? 100 : 50
  for (let s = Math.ceil(sMin / tickStep) * tickStep; s <= sMax; s += tickStep) {
    speedTicks.push({ x: pad.l + ((s - sMin) / span) * innerW, label: String(s) })
  }
  const angleTicks: { y: number; label: string }[] = []
  for (let a = 0; a <= 360; a += 90) {
    angleTicks.push({ y: pad.t + (a / 360) * innerH, label: `${a}°` })
  }
  return { width, height, cells, speedTicks, angleTicks }
}
