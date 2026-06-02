import { describe, expect, it } from 'vitest'

import { angleClass, axesMapConfig, mappingArrow, matchVerdict, statusBg } from '../axesMap'
import type { AxesMapResult } from '../types'

function result(over: Partial<AxesMapResult>): AxesMapResult {
  return {
    axes_map: 'x, y, z',
    chip: 'adxl345',
    status: 'ok',
    messages: [],
    mappings: [],
    euler: { x: 0, y: 0, z: 0 },
    gravity: 9.81,
    noise: 50,
    noise_grade: 'ok',
    current_axes_map: null,
    matches_current: null,
    accel: 1500,
    extrapolated_axis: null,
    velocity_series: [],
    source_files: [],
    ...over,
  }
}

describe('axesMap helpers', () => {
  it('builds a paste-ready config with the detected chip section', () => {
    expect(axesMapConfig(result({ chip: 'lis2dw', axes_map: '-z, y, x' }))).toBe(
      '[lis2dw]\naxes_map: -z, y, x',
    )
  })

  it('maps status to a badge background', () => {
    expect(statusBg('ok')).toContain('lime')
    expect(statusBg('warning')).toContain('yellow')
    expect(statusBg('error')).toContain('red')
  })

  it('formats a mapping arrow', () => {
    expect(
      mappingArrow({
        machine_axis: 'x',
        accel_axis: 'z',
        sign: '-',
        angle_error: 2,
        confidence: 1,
        extrapolated: false,
      }),
    ).toBe('X → -z')
  })

  it('grades the angle error', () => {
    expect(angleClass(3)).toContain('lime')
    expect(angleClass(10)).toContain('yellow')
    expect(angleClass(20)).toContain('red')
  })

  it('gives match guidance for each case', () => {
    expect(matchVerdict(result({ matches_current: true }))).toContain('already correct')
    expect(matchVerdict(result({ matches_current: false, axes_map: '-z, y, x' }))).toContain(
      '-z, y, x',
    )
    expect(matchVerdict(result({ matches_current: null }))).toContain('aligned')
  })
})
