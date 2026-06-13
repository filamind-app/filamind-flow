/** Pure builders for the sustain-frequency view: a frequency×time heatmap and an
 *  energy-vs-time "touch timeline". Dependency-free SVG (rects + a polyline); the
 *  power→colour ramp is a small JS interpolation over the brand palette.
 */

import type { StaticExcitationResult } from './types'

export interface HeatCell {
  x: number
  y: number
  w: number
  h: number
  fill: string
}

export interface SpectrogramChart {
  width: number
  height: number
  cells: HeatCell[]
  freqTicks: { x: number; label: string }[]
  /** x of the requested-frequency guide line (null if out of range). */
  guideX: number | null
}

export interface EnergyChart {
  width: number
  height: number
  points: string
  /** The lowest-energy point — where a touch likely helped. */
  minMark: { x: number; y: number } | null
}

type RGB = [number, number, number]

// paper → cyan → yellow → red (low to high power). Each stop is sourced from a theme
// token so the heatmap recolors per theme; the literals are only fallbacks (= the
// light-theme brand values) used when a CSS var can't be read (e.g. SSR / tests).
const STOPS: [number, string, RGB][] = [
  [0.0, '--c-paper', [245, 241, 232]],
  [0.4, '--c-brand-cyan', [0, 224, 198]],
  [0.7, '--c-brand-yellow', [140, 106, 74]],
  [1.0, '--c-brand-red', [255, 82, 71]],
]

/** Reads a space-separated RGB triplet CSS var (e.g. "0 224 198"), falling back to
 *  the supplied default when unavailable or unparseable. */
function readToken(name: string, fallback: RGB): RGB {
  if (typeof window === 'undefined' || typeof getComputedStyle !== 'function') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const parts = raw.split(/[\s,]+/).map(Number)
  return parts.length === 3 && parts.every((n) => Number.isFinite(n)) ? (parts as RGB) : fallback
}

/** Maps a 0..1 power to a theme-palette rgb() string. */
export function ramp(value: number): string {
  const stops: [number, RGB][] = STOPS.map(([pos, token, fallback]) => [
    pos,
    readToken(token, fallback),
  ])
  const x = Math.max(0, Math.min(1, value))
  for (let i = 1; i < stops.length; i++) {
    if (x <= stops[i][0]) {
      const [x0, c0] = stops[i - 1]
      const [x1, c1] = stops[i]
      const t = (x - x0) / (x1 - x0 || 1)
      const c = c0.map((v, k) => Math.round(v + (c1[k] - v) * t))
      return `rgb(${c[0]},${c[1]},${c[2]})`
    }
  }
  const last = stops[stops.length - 1][1]
  return `rgb(${last[0]},${last[1]},${last[2]})`
}

/** Frequency (x) × time (y) heatmap of the spectrogram power. */
export function buildSpectrogram(
  result: StaticExcitationResult,
  width = 320,
  height = 120,
): SpectrogramChart {
  const pad = { l: 4, r: 4, t: 6, b: 12 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const { freqs, times, spectrogram } = result
  if (!freqs.length || !times.length) {
    return { width, height, cells: [], freqTicks: [], guideX: null }
  }
  const fMax = freqs[freqs.length - 1] || 1
  const cellW = innerW / freqs.length
  const cellH = innerH / times.length
  const cells: HeatCell[] = []
  for (let fi = 0; fi < freqs.length; fi++) {
    const col = spectrogram[fi] ?? []
    for (let ti = 0; ti < times.length; ti++) {
      cells.push({
        x: pad.l + fi * cellW,
        y: pad.t + ti * cellH,
        w: cellW + 0.6,
        h: cellH + 0.6,
        fill: ramp(col[ti] ?? 0),
      })
    }
  }
  const freqTicks: { x: number; label: string }[] = []
  for (let f = 0; f <= fMax; f += 50)
    freqTicks.push({ x: pad.l + (f / fMax) * innerW, label: String(f) })
  const guideX = result.freq <= fMax ? pad.l + (result.freq / fMax) * innerW : null
  return { width, height, cells, freqTicks, guideX }
}

/** Energy vs time — the dip marks when touching a part reduced the vibration. */
export function buildEnergyTimeline(
  result: StaticExcitationResult,
  width = 320,
  height = 44,
): EnergyChart {
  const pad = { l: 4, r: 4, t: 4, b: 10 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const { energy } = result
  if (energy.length < 2) return { width, height, points: '', minMark: null }
  const n = energy.length
  const xAt = (i: number): number => pad.l + (i / (n - 1)) * innerW
  const yAt = (v: number): number => pad.t + innerH - Math.max(0, Math.min(1, v)) * innerH
  const points = energy.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
  let minI = 0
  for (let i = 1; i < n; i++) if (energy[i] < energy[minI]) minI = i
  return { width, height, points, minMark: { x: xAt(minI), y: yAt(energy[minI]) } }
}
