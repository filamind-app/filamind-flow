/** Pure comparison of two resonance analyses (e.g. before/after a mechanical fix,
 *  or the same axis re-tested). Produces a metric table + an overlaid PSD chart.
 *  Read-only; never mutates the inputs.
 */

import { i18n } from '@/core/i18n'

import type { PlotSeries } from './chart'
import type { ShaperAnalysis, ShaperResult } from './types'

export interface CompareRow {
  label: string
  a: string
  b: string
  /** Direction of change A→B, where one is meaningful (else 'neutral'). */
  trend: 'better' | 'worse' | 'same' | 'neutral'
}

export interface ComparePlot {
  width: number
  height: number
  /** Overlaid total-PSD (X+Y+Z) curves, scaled to shared axes. */
  a: PlotSeries
  b: PlotSeries
  xTicks: { x: number; label: string }[]
}

function fmtHz(value: number | null): string {
  return value == null
    ? '—'
    : i18n.global.t('inputShaping.compare.hz.value', { value: value.toFixed(1) })
}

function recommended(an: ShaperAnalysis): ShaperResult | null {
  return an.shapers.find((s) => s.recommended) ?? null
}

function peakFreq(an: ShaperAnalysis): number {
  let idx = 0
  let max = -Infinity
  an.psd_sum.forEach((v, i) => {
    if (v > max) {
      max = v
      idx = i
    }
  })
  return an.freqs[idx] ?? 0
}

function numTrend(a: number, b: number, lowerIsBetter: boolean): CompareRow['trend'] {
  if (Math.abs(a - b) < 1e-9) return 'same'
  const improved = lowerIsBetter ? b < a : b > a
  return improved ? 'better' : 'worse'
}

/** Builds the side-by-side metric rows for two analyses. */
export function compareAnalyses(a: ShaperAnalysis, b: ShaperAnalysis): CompareRow[] {
  const ra = recommended(a)
  const rb = recommended(b)
  const rows: CompareRow[] = [
    {
      label: i18n.global.t('inputShaping.compare.row.recommended'),
      a: (a.recommended_shaper ?? '—').toUpperCase(),
      b: (b.recommended_shaper ?? '—').toUpperCase(),
      trend: a.recommended_shaper === b.recommended_shaper ? 'same' : 'neutral',
    },
    {
      label: i18n.global.t('inputShaping.compare.row.shaperFreq'),
      a: fmtHz(a.recommended_freq),
      b: fmtHz(b.recommended_freq),
      trend: 'neutral',
    },
    {
      label: i18n.global.t('inputShaping.compare.row.peakFreq'),
      a: fmtHz(peakFreq(a)),
      b: fmtHz(peakFreq(b)),
      trend: 'neutral',
    },
  ]
  if (ra && rb) {
    rows.push(
      {
        label: i18n.global.t('inputShaping.compare.row.remainingVibr'),
        a: i18n.global.t('inputShaping.compare.pct.value', { value: ra.vibrations_pct.toFixed(1) }),
        b: i18n.global.t('inputShaping.compare.pct.value', { value: rb.vibrations_pct.toFixed(1) }),
        trend: numTrend(ra.vibrations_pct, rb.vibrations_pct, true),
      },
      {
        label: i18n.global.t('inputShaping.compare.row.maxAccel'),
        a: ra.max_accel.toFixed(0),
        b: rb.max_accel.toFixed(0),
        trend: numTrend(ra.max_accel, rb.max_accel, false),
      },
    )
  }
  return rows
}

/** Overlays the two total-PSD curves on shared axes for a visual A vs B. */
export function buildCompareChart(
  a: ShaperAnalysis,
  b: ShaperAnalysis,
  width = 320,
  height = 130,
): ComparePlot {
  const pad = { l: 4, r: 4, t: 6, b: 12 }
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const fMax = Math.max(a.freqs[a.freqs.length - 1] ?? 0, b.freqs[b.freqs.length - 1] ?? 0) || 1
  const yMax = Math.max(1e-12, ...a.psd_sum, ...b.psd_sum)
  const xAt = (f: number): number => pad.l + (f / fMax) * innerW
  const poly = (an: ShaperAnalysis): string =>
    an.freqs
      .map(
        (f, i) =>
          `${xAt(f).toFixed(1)},${(pad.t + innerH - (an.psd_sum[i] / yMax) * innerH).toFixed(1)}`,
      )
      .join(' ')

  const xTicks: { x: number; label: string }[] = []
  for (let f = 0; f <= fMax; f += 50) xTicks.push({ x: xAt(f), label: String(f) })

  return {
    width,
    height,
    a: { name: 'A', color: '#5b8cff', dashed: false, points: poly(a) },
    b: { name: 'B', color: '#ff5247', dashed: true, points: poly(b) },
    xTicks,
  }
}

export interface BeltVerdict {
  matched: boolean
  /** Dominant peak frequency of each belt (Hz). */
  peakA: number
  peakB: number
  /** Difference of the peak frequencies, as a percentage of the larger. */
  diffPct: number
  level: 'good' | 'warn'
  title: string
  advice: string
}

/** Belts whose dominant resonances are within this % are considered matched. */
const BELT_MATCH_PCT = 10

/** Judges two CoreXY belt-direction captures: matched tension vs a mismatch. */
export function beltVerdict(a: ShaperAnalysis, b: ShaperAnalysis): BeltVerdict {
  const peakA = peakFreq(a)
  const peakB = peakFreq(b)
  const diffPct = (Math.abs(peakA - peakB) / Math.max(peakA, peakB, 1)) * 100
  if (diffPct < BELT_MATCH_PCT) {
    return {
      matched: true,
      peakA,
      peakB,
      diffPct,
      level: 'good',
      title: i18n.global.t('inputShaping.compare.belt.matched.title'),
      advice: i18n.global.t('inputShaping.compare.belt.matched.advice'),
    }
  }
  return {
    matched: false,
    peakA,
    peakB,
    diffPct,
    level: 'warn',
    title: i18n.global.t('inputShaping.compare.belt.differ.title'),
    advice: i18n.global.t('inputShaping.compare.belt.differ.advice'),
  }
}
