import { describe, expect, it } from 'vitest'

import { gateBelts, gateNoise, gateShaper, nextStep, STEPS } from '../guided'
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

describe('guided', () => {
  it('advances through the steps and stops at done', () => {
    expect(STEPS[0].id).toBe('noise')
    expect(nextStep('noise')).toBe('belts')
    expect(nextStep('shaperY')).toBe('vibrations')
    expect(nextStep('vibrations')).toBe('pressure')
    expect(nextStep('pressure')).toBe('done')
    expect(nextStep('done')).toBe('done')
  })

  it('marks the vibrations + pressure steps as manual', () => {
    const manual = STEPS.filter((s) => s.manual).map((s) => s.id)
    expect(manual).toEqual(['vibrations', 'pressure'])
  })

  it('gates noise by grade', () => {
    expect(gateNoise(noise({ grade: 'good' })).status).toBe('passed')
    expect(gateNoise(noise({ grade: 'elevated' })).status).toBe('warn')
    expect(gateNoise(noise({ grade: 'high' })).status).toBe('failed')
  })

  it('gates the shaper by its A–F grade', () => {
    expect(gateShaper(analysis({})).status).toBe('passed') // clean MZV → A
    const poor = analysis({
      recommended_shaper: '3hump_ei',
      recommended_freq: 24,
      shapers: [shaper({ name: '3hump_ei', freq: 24, vibrations_pct: 8, smoothing: 0.3 })],
      psd_sum: [1, 1.2, 1],
    })
    expect(gateShaper(poor).status).toBe('failed')
  })

  it('gates belts: matched passes, a big mismatch fails', () => {
    const a = analysis({ freqs: [40, 50, 60], psd_sum: [1, 9, 2] }) // peak 50
    const b = analysis({ freqs: [40, 50, 60], psd_sum: [1, 8, 3] }) // peak 50
    expect(gateBelts(a, b).status).toBe('passed')
    const c = analysis({ freqs: [40, 50, 60, 80], psd_sum: [1, 9, 2, 1] }) // peak 50
    const d = analysis({ freqs: [40, 50, 60, 80], psd_sum: [1, 1, 1, 9] }) // peak 80
    expect(gateBelts(c, d).status).toBe('failed') // Δ ~37% > 25
  })
})
