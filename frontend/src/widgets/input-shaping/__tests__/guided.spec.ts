import { describe, expect, it } from 'vitest'

import { gateBelts, gateNoise, gateShaper, gateVibrations, nextStep, STEPS } from '../guided'
import type { NoiseResult, ShaperAnalysis, ShaperResult, VibrationsProfile } from '../types'

function vib(over: Partial<VibrationsProfile>): VibrationsProfile {
  return {
    kinematics: 'corexy',
    accel: 3000,
    max_freq: 200,
    main_angles: [45, 135],
    segments_used: 40,
    segments_captured: 40,
    speeds: [20, 60, 100],
    energy_profile: [0.2, 1, 0.3],
    max_profile: [0.3, 1, 0.4],
    peak_speeds: [60],
    good_speed_ranges: [{ start: 80, end: 100, energy_pct: 20 }],
    angles: [0, 90, 180, 270],
    angle_energy: [0.5, 1, 0.5, 1],
    good_angle_ranges: [],
    symmetry_pct: 90,
    motor_freq: 55,
    motor_damping: 0.1,
    low_freq_warning: false,
    spectrogram: [[0.5]],
    recommended_speed: 90,
    verdict: 'ok',
    ...over,
  }
}

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

  it('vibrations is now a measured (motion) step; only pressure stays manual', () => {
    expect(STEPS.filter((s) => s.manual).map((s) => s.id)).toEqual(['pressure'])
    expect(STEPS.find((s) => s.id === 'vibrations')?.motion).toBe(true)
  })

  it('gates the vibrations profile: smooth passes, low symmetry warns, low-freq fails', () => {
    expect(gateVibrations(vib({})).status).toBe('passed')
    expect(gateVibrations(vib({ symmetry_pct: 40 })).status).toBe('warn')
    expect(gateVibrations(vib({ low_freq_warning: true })).status).toBe('failed')
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
