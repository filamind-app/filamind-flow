import { describe, expect, it } from 'vitest'

import type { VibrationsProfile } from '../types'
import { buildPolarAngles, buildSpeedProfile, buildVibHeatmap } from '../vibrations'

function vib(over: Partial<VibrationsProfile> = {}): VibrationsProfile {
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
    angles: [0, 90, 180, 270, 360],
    angle_energy: [0.5, 1, 0.5, 1, 0.5],
    good_angle_ranges: [{ start: 20, end: 70, energy_pct: 30 }],
    symmetry_pct: 95,
    motor_freq: 55,
    motor_damping: 0.1,
    low_freq_warning: false,
    spectrogram: [
      [0.1, 0.2, 0.9, 0.3, 0.2],
      [0.2, 0.3, 1, 0.4, 0.3],
      [0.1, 0.2, 0.8, 0.3, 0.2],
      [0.2, 0.3, 1, 0.4, 0.3],
      [0.1, 0.2, 0.9, 0.3, 0.2],
    ],
    recommended_speed: 165,
    verdict: 'ok',
    ...over,
  }
}

describe('vibrations chart builders', () => {
  it('buildSpeedProfile marks bands, peaks and the recommended speed', () => {
    const c = buildSpeedProfile(vib())
    expect(c.energyPoints.split(' ').length).toBe(5)
    expect(c.maxPoints.split(' ').length).toBe(5)
    expect(c.bands.length).toBe(1)
    expect(c.peaks.length).toBe(1)
    expect(c.recommendedX).not.toBeNull()
    expect(c.speedTicks.length).toBeGreaterThan(0)
  })

  it('buildSpeedProfile degrades gracefully with too few speeds', () => {
    const c = buildSpeedProfile(vib({ speeds: [50], energy_profile: [1], max_profile: [1] }))
    expect(c.energyPoints).toBe('')
    expect(c.bands).toEqual([])
  })

  it('buildPolarAngles closes a polygon with one point per angle + motor spokes', () => {
    const p = buildPolarAngles(vib())
    expect(p.polygon.split(' ').length).toBe(5)
    expect(p.spokes.length).toBe(2)
    expect(p.spokes.map((s) => s.label)).toEqual(['45°', '135°'])
  })

  it('buildVibHeatmap fills an angle × speed grid with axis ticks', () => {
    const h = buildVibHeatmap(vib())
    expect(h.cells.length).toBe(5 * 5) // angles × speeds
    expect(h.angleTicks.map((t) => t.label)).toEqual(['0°', '90°', '180°', '270°', '360°'])
    expect(h.speedTicks.length).toBeGreaterThan(0)
    // Every cell carries a colour.
    expect(h.cells.every((c) => c.fill.startsWith('rgb('))).toBe(true)
  })
})
