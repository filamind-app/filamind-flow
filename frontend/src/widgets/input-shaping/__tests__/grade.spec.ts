import { describe, expect, it } from 'vitest'

import { gradeAnalysis } from '../grade'
import type { ShaperAnalysis, ShaperResult } from '../types'

function shaper(over: Partial<ShaperResult>): ShaperResult {
  return {
    name: 'mzv',
    freq: 57,
    vibrations_pct: 1,
    smoothing: 0.08,
    max_accel: 7000,
    recommended: true,
    ...over,
  }
}

function analysis(over: Partial<ShaperAnalysis>): ShaperAnalysis {
  return {
    recommended_shaper: 'mzv',
    recommended_freq: 57,
    axis: null,
    max_freq: 200,
    shapers: [shaper({})],
    freqs: [],
    psd_x: [],
    psd_y: [],
    psd_z: [],
    psd_sum: [1, 1, 20, 1, 1], // a clean peak well above the noise
    shaper_curves: [],
    log: [],
    source_file: null,
    ...over,
  }
}

describe('gradeAnalysis', () => {
  it('grades a clean MZV @ 57 Hz capture as A', () => {
    const g = gradeAnalysis(analysis({}))
    expect(g.letter).toBe('A')
    expect(g.score).toBeGreaterThanOrEqual(85)
    expect(g.factors).toHaveLength(5)
    expect(g.factors.find((f) => f.label === 'Peak clarity')?.rating).toBe('good')
  })

  it('downgrades a soft, noisy, heavily-smoothed multi-hump result', () => {
    const g = gradeAnalysis(
      analysis({
        recommended_shaper: '3hump_ei',
        recommended_freq: 24,
        shapers: [shaper({ name: '3hump_ei', freq: 24, vibrations_pct: 8, smoothing: 0.3 })],
        psd_sum: [1, 1, 1.2, 1, 1], // barely-there peak → poor clarity
      }),
    )
    expect(['D', 'F']).toContain(g.letter)
    expect(g.score).toBeLessThan(55)
  })

  it('returns F when there is no recommendation', () => {
    const g = gradeAnalysis(
      analysis({ recommended_shaper: null, recommended_freq: null, shapers: [] }),
    )
    expect(g.letter).toBe('F')
    expect(g.score).toBe(0)
  })
})
