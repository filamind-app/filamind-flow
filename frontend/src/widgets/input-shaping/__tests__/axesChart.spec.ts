import { describe, expect, it } from 'vitest'

import { buildAxesVelocityChart } from '../axesChart'
import type { VelocitySeries } from '../types'

function seg(over: Partial<VelocitySeries>): VelocitySeries {
  return {
    axis: 'x',
    t: [0, 0.5, 1],
    vx: [0, 5, 0],
    vy: [0, 0, 0],
    vz: [0, 0, 0],
    detected_axis: '+x',
    confidence: 1,
    extrapolated: false,
    ...over,
  }
}

describe('buildAxesVelocityChart', () => {
  it('returns empty zones when there is no data', () => {
    const chart = buildAxesVelocityChart([])
    expect(chart.zones).toEqual([])
    expect(chart.boundaries).toEqual([])
  })

  it('builds one zone per segment, a divider between, and per-axis polylines', () => {
    const chart = buildAxesVelocityChart([
      seg({ axis: 'x' }),
      seg({ axis: 'y', detected_axis: '+y' }),
    ])
    expect(chart.zones).toHaveLength(2)
    expect(chart.boundaries).toHaveLength(1)
    expect(chart.zones[0].vx.split(' ')).toHaveLength(3)
    expect(chart.zones[0].axis).toBe('X')
    expect(chart.zones[1].detected).toBe('+y')
  })
})
