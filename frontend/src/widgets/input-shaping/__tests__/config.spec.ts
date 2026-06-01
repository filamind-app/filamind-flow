import { describe, expect, it } from 'vitest'

import { inputShaperConfig } from '../config'
import type { ShaperAnalysis } from '../types'

function analysis(over: Partial<ShaperAnalysis>): ShaperAnalysis {
  return {
    recommended_shaper: 'mzv',
    recommended_freq: 52.3,
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
    ...over,
  }
}

describe('inputShaperConfig', () => {
  it('emits axis-specific keys for known axes, rounded to 0.1 Hz', () => {
    const cfg = inputShaperConfig([
      analysis({ axis: 'x', recommended_shaper: 'mzv', recommended_freq: 52.34 }),
      analysis({ axis: 'y', recommended_shaper: 'ei', recommended_freq: 41.6 }),
    ])
    expect(cfg).toBe(
      [
        '[input_shaper]',
        'shaper_type_x: mzv',
        'shaper_freq_x: 52.3',
        'shaper_type_y: ei',
        'shaper_freq_y: 41.6',
      ].join('\n'),
    )
  })

  it('emits generic keys when no axis is given', () => {
    const cfg = inputShaperConfig([
      analysis({ axis: null, recommended_shaper: 'zv', recommended_freq: 60 }),
    ])
    expect(cfg).toBe('[input_shaper]\nshaper_type: zv\nshaper_freq: 60.0')
  })

  it('skips an analysis with no recommendation', () => {
    expect(
      inputShaperConfig([analysis({ recommended_shaper: null, recommended_freq: null })]),
    ).toBe('[input_shaper]')
  })
})
