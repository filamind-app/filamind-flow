import { describe, expect, it } from 'vitest'

import { interpret } from '../interpret'
import type { ShaperAnalysis, ShaperResult } from '../types'

function shaper(over: Partial<ShaperResult>): ShaperResult {
  return {
    name: 'mzv',
    freq: 50,
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
    source_file: null,
    ...over,
  }
}

describe('interpret', () => {
  it('warns when there is no recommendation', () => {
    const hints = interpret(analysis({ recommended_shaper: null, shapers: [] }))
    expect(hints).toHaveLength(1)
    expect(hints[0].level).toBe('warn')
  })

  it('flags low frequency and high smoothing (plus the max_accel hint)', () => {
    const hints = interpret(
      analysis({
        recommended_shaper: 'ei',
        recommended_freq: 22,
        shapers: [shaper({ name: 'ei', freq: 22, smoothing: 0.25, max_accel: 2500 })],
      }),
    )
    expect(hints.some((h) => h.text.includes('max_accel'))).toBe(true)
    expect(hints.some((h) => h.level === 'warn' && /Low shaper frequency/.test(h.text))).toBe(true)
    expect(hints.some((h) => h.level === 'warn' && /High smoothing/.test(h.text))).toBe(true)
  })

  it('is quiet for a healthy result (just the max_accel hint)', () => {
    const hints = interpret(
      analysis({
        recommended_shaper: 'mzv',
        recommended_freq: 55,
        shapers: [shaper({ freq: 55 })],
      }),
    )
    expect(hints).toHaveLength(1)
    expect(hints[0].level).toBe('info')
  })
})
