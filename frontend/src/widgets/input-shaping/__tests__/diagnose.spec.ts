import { describe, expect, it } from 'vitest'

import { diagnose, diagnoseAxes } from '../diagnose'
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
    psd_sum: [1, 1, 20, 1, 1],
    shaper_curves: [],
    log: [],
    source_file: null,
    ...over,
  }
}

describe('diagnose', () => {
  it('reports a healthy axis for a clean result', () => {
    const ds = diagnose(analysis({}))
    expect(ds).toHaveLength(1)
    expect(ds[0].level).toBe('good')
    expect(ds[0].illo).toBe('ok')
  })

  it('flags low frequency with a belt illustration', () => {
    const ds = diagnose(analysis({ recommended_freq: 22, shapers: [shaper({ freq: 22 })] }))
    const low = ds.find((d) => d.title === 'Low resonance frequency')
    expect(low?.level).toBe('bad')
    expect(low?.illo).toBe('belt')
  })

  it('flags high smoothing and a multi-hump shaper', () => {
    const ds = diagnose(
      analysis({
        recommended_shaper: '2hump_ei',
        shapers: [shaper({ name: '2hump_ei', smoothing: 0.25 })],
      }),
    )
    expect(ds.some((d) => d.title === 'High smoothing' && d.illo === 'tune')).toBe(true)
    expect(ds.some((d) => d.title === 'Multiple resonances' && d.illo === 'toolhead')).toBe(true)
  })

  it('flags a noisy capture from a weak peak', () => {
    const ds = diagnose(analysis({ psd_sum: [1, 1, 1.1, 1, 1] }))
    expect(ds.some((d) => d.title === 'Noisy capture' && d.illo === 'accel')).toBe(true)
  })

  it('returns a single bad card when nothing is recommended', () => {
    const ds = diagnose(analysis({ recommended_shaper: null, shapers: [] }))
    expect(ds).toHaveLength(1)
    expect(ds[0].level).toBe('bad')
  })
})

describe('diagnoseAxes', () => {
  it('flags a big X/Y stiffness mismatch with a balance illustration', () => {
    const d = diagnoseAxes(analysis({ recommended_freq: 40 }), analysis({ recommended_freq: 70 }))
    expect(d?.illo).toBe('balance')
    expect(d?.level).toBe('warn')
  })

  it('is quiet when the axes are close', () => {
    expect(
      diagnoseAxes(analysis({ recommended_freq: 55 }), analysis({ recommended_freq: 58 })),
    ).toBeNull()
  })
})
