import { describe, expect, it } from 'vitest'

import type { BeltVerdict } from '../compare'
import {
  recommendBelts,
  recommendNoise,
  recommendPressure,
  recommendShaper,
  recommendVibrations,
} from '../recommend'
import type { NoiseResult, ShaperAnalysis, ShaperResult, VibrationsProfile } from '../types'

function noise(over: Partial<NoiseResult>): NoiseResult {
  return { chips: [], max_noise: 50, grade: 'good', ok: true, threshold: 100, ...over }
}
function vib(over: Partial<VibrationsProfile>): VibrationsProfile {
  return {
    kinematics: 'corexy',
    accel: 3000,
    max_freq: 200,
    main_angles: [45, 135],
    segments_used: 40,
    segments_captured: 40,
    speeds: [20, 60, 100, 140, 180],
    energy_profile: [0.2, 0.4, 1, 0.5, 0.3],
    max_profile: [0.3, 0.5, 1, 0.6, 0.4],
    peak_speeds: [100],
    good_speed_ranges: [{ start: 150, end: 180, energy_pct: 20 }],
    angles: [0, 90, 180, 270],
    angle_energy: [0.5, 1, 0.5, 1],
    good_angle_ranges: [{ start: 20, end: 70, energy_pct: 30 }],
    symmetry_pct: 95,
    motor_freq: 55,
    motor_damping: 0.1,
    low_freq_warning: false,
    spectrogram: [[0.5]],
    recommended_speed: 165,
    verdict: 'ok',
    ...over,
  }
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

  it('vibrations → ok smooth speed + consider avoid-speeds; do-now on low-freq noise', () => {
    const s = recommendVibrations(vib({}))
    expect(s[0].level).toBe('ok')
    expect(s[0].title).toContain('165')
    expect(s.some((x) => x.level === 'consider' && x.title.includes('100'))).toBe(true)
    expect(recommendVibrations(vib({ low_freq_warning: true }))[0].level).toBe('do-now')
    expect(recommendVibrations(vib({ symmetry_pct: 40 })).some((x) => x.level === 'do-now')).toBe(
      true,
    )
  })

  it('pressure → a do-now PA-tower step', () => {
    expect(recommendPressure()[0].level).toBe('do-now')
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
