import { describe, expect, it } from 'vitest'

import type { AuditRecord } from '../audit'
import { buildProofRows, proofCandidates, proofText } from '../proof'

function rec(over: Partial<AuditRecord>): AuditRecord {
  return {
    id: 'r',
    at: '2026-06-01T00:00:00',
    kind: 'shaper',
    axis: 'x',
    source: 'local',
    fields: [],
    ...over,
  } as AuditRecord
}

describe('proofCandidates', () => {
  it('keeps only same-axis shaper/config records that carry numbers', () => {
    const records = [
      rec({ id: 'a', grade: { letter: 'B', score: 80 } }),
      rec({ id: 'b', axis: 'y', grade: { letter: 'A', score: 95 } }),
      rec({ id: 'c', kind: 'noise', grade: { letter: 'A', score: 95 } }),
      rec({ id: 'd' }), // no grade, no metrics
      rec({ id: 'e', kind: 'config', metrics: { freq: 57 } }),
    ]
    expect(proofCandidates(records, 'x').map((r) => r.id)).toEqual(['a', 'e'])
  })
})

describe('buildProofRows', () => {
  const before = rec({
    id: 'b',
    grade: { letter: 'C', score: 70 },
    metrics: { shaper: 'mzv', freq: 52.0, vibrations_pct: 8.4, smoothing: 0.11, max_accel: 3500 },
  })
  const after = rec({
    id: 'a',
    grade: { letter: 'A', score: 92 },
    metrics: { shaper: 'ei', freq: 57.5, vibrations_pct: 2.1, smoothing: 0.08, max_accel: 4200 },
  })

  it('marks score up and vibration down as improvements', () => {
    const rows = buildProofRows(before, after)
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]))
    expect(byKey.score.better).toBe(true)
    expect(byKey.score.delta).toBe('+22')
    expect(byKey.vibrations.better).toBe(true) // lower is better
    expect(byKey.vibrations.delta).toBe('−6.3')
    expect(byKey.smoothing.better).toBe(true)
    expect(byKey.maxAccel.better).toBe(true)
    expect(byKey.freq.better).toBeNull() // informational, not scored
    expect(byKey.shaper.before).toBe('MZV')
    expect(byKey.shaper.after).toBe('EI')
  })

  it('renders dashes and no delta when a side has no metrics', () => {
    const rows = buildProofRows(rec({ id: 'b', grade: { letter: 'C', score: 70 } }), after)
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]))
    expect(byKey.vibrations.before).toBe('—')
    expect(byKey.vibrations.delta).toBe('')
    expect(byKey.vibrations.better).toBeNull()
    expect(byKey.score.delta).toBe('+22')
  })

  it('flags a regression', () => {
    const rows = buildProofRows(after, before)
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]))
    expect(byKey.score.better).toBe(false)
    expect(byKey.vibrations.better).toBe(false)
  })
})

describe('proofText', () => {
  it('builds a plain-text report with deltas', () => {
    const rows = buildProofRows(
      rec({ id: 'b', grade: { letter: 'C', score: 70 } }),
      rec({ id: 'a', grade: { letter: 'A', score: 92 } }),
    )
    const text = proofText('Proof of tune', 'x', '1/1', '2/2', [{ label: 'Grade', row: rows[0] }])
    expect(text).toContain('axis X · 1/1 → 2/2')
    expect(text).toContain('Grade: C (70) → A (92) (+22)')
  })
})
