import { describe, expect, it } from 'vitest'

import { buildCompareChart, compareAnalyses } from '../compare'
import type { ShaperAnalysis, ShaperResult } from '../types'

function shaper(over: Partial<ShaperResult>): ShaperResult {
  return {
    name: 'mzv',
    freq: 50,
    vibrations_pct: 5,
    smoothing: 0.1,
    max_accel: 3000,
    recommended: true,
    ...over,
  }
}

function analysis(over: Partial<ShaperAnalysis>): ShaperAnalysis {
  return {
    recommended_shaper: 'mzv',
    recommended_freq: 50,
    axis: null,
    max_freq: 200,
    shapers: [],
    freqs: [],
    psd_x: [],
    psd_y: [],
    psd_z: [],
    psd_sum: [],
    shaper_curves: [],
    log: [],
    ...over,
  }
}

describe('compareAnalyses', () => {
  it('flags improvements A→B (lower vibration + higher accel = better)', () => {
    const a = analysis({
      recommended_shaper: 'mzv',
      recommended_freq: 50,
      freqs: [40, 50, 60],
      psd_sum: [1, 9, 2],
      shapers: [shaper({ vibrations_pct: 8, max_accel: 3000 })],
    })
    const b = analysis({
      recommended_shaper: 'mzv',
      recommended_freq: 55,
      freqs: [40, 50, 60],
      psd_sum: [1, 4, 2],
      shapers: [shaper({ freq: 55, vibrations_pct: 3, max_accel: 5000 })],
    })
    const rows = Object.fromEntries(compareAnalyses(a, b).map((r) => [r.label, r]))

    expect(rows['recommended'].trend).toBe('same')
    expect(rows['peak freq'].a).toBe('50.0 Hz') // argmax(psd_sum) → 50 Hz
    expect(rows['remaining vibr'].trend).toBe('better') // 8% → 3%
    expect(rows['max_accel'].trend).toBe('better') // 3000 → 5000
  })

  it('marks a worse max_accel correctly', () => {
    const a = analysis({ shapers: [shaper({ max_accel: 6000 })] })
    const b = analysis({ shapers: [shaper({ max_accel: 4000 })] })
    const rows = Object.fromEntries(compareAnalyses(a, b).map((r) => [r.label, r]))
    expect(rows['max_accel'].trend).toBe('worse')
  })
})

describe('buildCompareChart', () => {
  it('overlays both PSD curves on shared axes', () => {
    const plot = buildCompareChart(
      analysis({ freqs: [0, 50, 100], psd_sum: [0, 10, 0] }),
      analysis({ freqs: [0, 50, 100], psd_sum: [0, 5, 0] }),
    )
    expect(plot.a.points.split(' ')).toHaveLength(3)
    expect(plot.b.points.split(' ')).toHaveLength(3)
    expect(plot.a.dashed).toBe(false)
    expect(plot.b.dashed).toBe(true)
    expect(plot.xTicks.map((t) => t.label)).toEqual(['0', '50', '100'])
  })
})
