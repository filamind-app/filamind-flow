import { describe, expect, it } from 'vitest'

import { buildResponseChart } from '../chart'
import type { ShaperAnalysis } from '../types'

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

describe('buildResponseChart', () => {
  it('returns empty series + no annotations when there is no data', () => {
    const chart = buildResponseChart(analysis({}))
    expect(chart.psd).toEqual([])
    expect(chart.shapers).toEqual([])
    expect(chart.xTicks).toEqual([])
    expect(chart.peak).toBeNull()
    expect(chart.noiseY).toBeNull()
  })

  it('annotates the dominant peak and the noise floor', () => {
    const chart = buildResponseChart(
      analysis({
        freqs: [0, 50, 100],
        psd_x: [0, 10, 0],
        psd_y: [0, 5, 0],
        psd_z: [0, 1, 0],
        psd_sum: [0, 16, 0],
      }),
      320,
      150,
    )
    expect(chart.peak?.freq).toBe(50)
    expect(chart.peak?.label).toBe('50 Hz')
    expect(chart.noiseY).not.toBeNull()
  })

  it('maps PSD + shaper series onto polyline points', () => {
    const chart = buildResponseChart(
      analysis({
        freqs: [0, 50, 100],
        psd_x: [0, 10, 0],
        psd_y: [0, 5, 0],
        psd_z: [0, 1, 0],
        psd_sum: [0, 16, 0],
        shaper_curves: [
          { name: 'mzv', vals: [1, 0.5, 0.2] },
          { name: 'zv', vals: [1, 0.7, 0.3] },
        ],
      }),
      320,
      150,
    )

    // Four PSD curves; each polyline has one point per frequency bin.
    expect(chart.psd.map((s) => s.name)).toEqual(['X+Y+Z', 'X', 'Y', 'Z'])
    expect(chart.psd[0].points.split(' ')).toHaveLength(3)

    // The recommended shaper is solid + accented; the other is dashed + grey.
    const mzv = chart.shapers.find((s) => s.name === 'mzv')!
    const zv = chart.shapers.find((s) => s.name === 'zv')!
    expect(mzv.dashed).toBe(false)
    expect(zv.dashed).toBe(true)
    expect(mzv.color).not.toBe(zv.color)

    // The PSD peak (50 Hz) maps to the top of the plot area; the troughs sit lower.
    const [x0y0, x50y50] = chart.psd[0].points.split(' ').map((p) => p.split(',').map(Number))
    expect(x50y50[1]).toBeLessThan(x0y0[1]) // smaller y = higher on screen

    // Ticks every 50 Hz across the 0..100 range.
    expect(chart.xTicks.map((t) => t.label)).toEqual(['0', '50', '100'])
  })
})
