import { beforeEach, describe, expect, it } from 'vitest'

import { addHistory, clearHistory, loadHistory, withTrends } from '../history'

describe('input-shaping history', () => {
  beforeEach(() => clearHistory())

  it('persists entries newest-first and caps the list at 20', () => {
    expect(loadHistory()).toEqual([])

    addHistory({ at: '2026-01-01T00:00:00Z', axis: 'x', shaper: 'mzv', freq: 50 })
    const list = addHistory({ at: '2026-01-02T00:00:00Z', axis: 'y', shaper: 'ei', freq: 40 })
    expect(list[0].axis).toBe('y') // newest first
    expect(loadHistory()).toHaveLength(2)

    for (let i = 0; i < 25; i++) addHistory({ at: `t${i}`, axis: null, shaper: 'zv', freq: i })
    expect(loadHistory()).toHaveLength(20)
  })

  it('clears the history', () => {
    addHistory({ at: 'x', axis: null, shaper: 'zv', freq: 1 })
    clearHistory()
    expect(loadHistory()).toEqual([])
  })
})

describe('withTrends', () => {
  it('trends each score against the previous same-axis calibration (newest-first)', () => {
    // Newest first: X improved 70→85, Y is a first-ever test, old X has no score.
    const trends = withTrends([
      { at: 't3', axis: 'x', shaper: 'mzv', freq: 57, grade: 'A', score: 85 },
      { at: 't2', axis: 'y', shaper: 'ei', freq: 45, grade: 'B', score: 78 },
      { at: 't1', axis: 'x', shaper: 'ei', freq: 40, grade: 'B', score: 70 },
      { at: 't0', axis: 'x', shaper: 'zv', freq: 38 }, // pre-v0.38, no score
    ])
    expect(trends[0].trend).toBe('up') // X 85 > previous X 70
    expect(trends[1].trend).toBe('none') // first Y test
    expect(trends[2].trend).toBe('none') // previous X entry has no score
    expect(trends[3].trend).toBe('none') // no score at all
  })

  it('marks a decline and a tie', () => {
    const down = withTrends([
      { at: 't1', axis: 'x', shaper: 'ei', freq: 30, grade: 'C', score: 60 },
      { at: 't0', axis: 'x', shaper: 'mzv', freq: 57, grade: 'A', score: 90 },
    ])
    expect(down[0].trend).toBe('down') // 60 < 90
    const same = withTrends([
      { at: 't1', axis: 'x', shaper: 'mzv', freq: 57, grade: 'A', score: 88 },
      { at: 't0', axis: 'x', shaper: 'mzv', freq: 57, grade: 'A', score: 88 },
    ])
    expect(same[0].trend).toBe('same')
  })
})
