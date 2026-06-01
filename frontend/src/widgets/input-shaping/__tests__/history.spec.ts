import { beforeEach, describe, expect, it } from 'vitest'

import { addHistory, clearHistory, loadHistory } from '../history'

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
