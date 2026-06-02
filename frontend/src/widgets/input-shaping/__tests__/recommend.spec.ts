import { describe, expect, it } from 'vitest'

import type { BeltVerdict } from '../compare'
import { recommendBelts, recommendNoise, recommendShaper } from '../recommend'
import type { NoiseResult, ShaperAnalysis, ShaperResult } from '../types'

function noise(over: Partial<NoiseResult>): NoiseResult {
  return { chips: [], max_noise: 50, grade: 'good', ok: true, threshold: 100, ...over }
}
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
    freqs: [40, 57, 80],
    psd_x: [],
    psd_y: [],
    psd_z: [],
    psd_sum: [1, 20, 1],
    shaper_curves: [],
    log: [],
    source_file: null,
    ...over,
  }
}

describe('recommend', () => {
  it('noise → ok / consider / do-now by grade', () => {
    expect(recommendNoise(noise({ grade: 'good' }))[0].level).toBe('ok')
    expect(recommendNoise(noise({ grade: 'elevated' }))[0].level).toBe('consider')
    expect(recommendNoise(noise({ grade: 'high' }))[0].level).toBe('do-now')
  })

  it('belts → names the looser (lower-frequency) belt on a mismatch', () => {
    const verdict: BeltVerdict = {
      matched: false,
      peakA: 40,
      peakB: 60,
      diffPct: 33,
      level: 'warn',
      title: 'Belts differ',
      advice: '',
    }
    const suggestions = recommendBelts(verdict)
    expect(suggestions[0].level).toBe('do-now')
    expect(suggestions[0].title).toContain('A (1,1)') // 40 Hz < 60 Hz → looser
  })

  it('shaper → maps diagnostics, worst (do-now) first', () => {
    const poor = analysis({
      recommended_shaper: '3hump_ei',
      recommended_freq: 22,
      shapers: [shaper({ name: '3hump_ei', freq: 22, smoothing: 0.3 })],
      psd_sum: [1, 1.1, 1],
    })
    const suggestions = recommendShaper(poor)
    expect(suggestions.length).toBeGreaterThan(0)
    expect(suggestions[0].level).toBe('do-now')
  })
})
