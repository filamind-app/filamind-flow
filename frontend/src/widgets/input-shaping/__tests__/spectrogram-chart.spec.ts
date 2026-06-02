import { describe, expect, it } from 'vitest'

import { buildEnergyTimeline, buildSpectrogram, ramp } from '../spectrogram-chart'
import type { StaticExcitationResult } from '../types'

function result(over: Partial<StaticExcitationResult>): StaticExcitationResult {
  return {
    axis: 'x',
    freq: 50,
    duration: 15,
    max_freq: 200,
    freqs: [0, 50, 100, 150, 200],
    times: [0, 1, 2],
    spectrogram: [
      [0, 0, 0],
      [0.2, 0.9, 0.1],
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    energy: [1, 0.3, 0.8],
    excited_band_pct: 60,
    energy_drop_pct: 70,
    dominant_freq: 50,
    dominant_ok: true,
    verdict: 'holding',
    source_file: null,
    ...over,
  }
}

describe('spectrogram-chart', () => {
  it('ramps power 0..1 across the palette', () => {
    expect(ramp(0)).toMatch(/^rgb\(/)
    expect(ramp(1)).toBe('rgb(255,82,71)')
    expect(ramp(0.5)).toMatch(/^rgb\(/)
  })

  it('builds a heatmap cell per freq×time + a freq guide line', () => {
    const chart = buildSpectrogram(result({}))
    expect(chart.cells).toHaveLength(5 * 3)
    expect(chart.guideX).not.toBeNull() // 50 Hz is within 0..200
    expect(chart.freqTicks.length).toBeGreaterThan(0)
  })

  it('returns empty cells when there is no data', () => {
    expect(buildSpectrogram(result({ freqs: [], times: [] })).cells).toEqual([])
  })

  it('builds an energy polyline and marks the lowest (touch-helped) point', () => {
    const energy = buildEnergyTimeline(result({ energy: [1, 0.2, 0.9] }))
    expect(energy.points.split(' ')).toHaveLength(3)
    expect(energy.minMark).not.toBeNull()
  })
})
