import { afterEach, describe, expect, it } from 'vitest'

import {
  clearGuidedSession,
  type GuidedSnapshot,
  loadGuidedSession,
  saveGuidedSession,
} from '../guided-store'
import type { NoiseResult, ShaperAnalysis } from '../types'

const KEY = 'filamind-guided-tune'

function sample(): GuidedSnapshot {
  return {
    idx: 2,
    statuses: { noise: 'passed', belts: 'skipped', shaperX: 'warn' },
    results: {
      noise: { overall_grade: 'A' } as unknown as NoiseResult,
      shaperX: { recommended_shaper: 'mzv', recommended_freq: 45 } as unknown as ShaperAnalysis,
    },
    verdicts: { noise: { status: 'passed', headline: 'Quiet' } },
    sugg: { noise: [{ level: 'ok', title: 'Good', why: 'Low noise' }] },
    archived: { shaperX: true },
    openCards: { shaperX: true },
    kinematics: 'corexy',
  }
}

afterEach(() => localStorage.clear())

describe('guided-store', () => {
  it('round-trips a saved session (finished stages are not lost)', () => {
    const snap = sample()
    saveGuidedSession(snap)
    expect(loadGuidedSession()).toEqual(snap)
  })

  it('returns null when nothing is saved', () => {
    expect(loadGuidedSession()).toBeNull()
  })

  it('clears the saved session on completion', () => {
    saveGuidedSession(sample())
    clearGuidedSession()
    expect(loadGuidedSession()).toBeNull()
  })

  it('ignores a snapshot written by an incompatible schema', () => {
    localStorage.setItem(KEY, JSON.stringify({ v: 999, idx: 3 }))
    expect(loadGuidedSession()).toBeNull()
  })

  it('ignores corrupt JSON without throwing', () => {
    localStorage.setItem(KEY, '{not valid json')
    expect(loadGuidedSession()).toBeNull()
  })

  it('rejects a same-schema snapshot missing its core sub-objects', () => {
    localStorage.setItem(KEY, JSON.stringify({ v: 1, idx: 2 })) // no statuses/results/etc.
    expect(loadGuidedSession()).toBeNull()
  })

  it('does not persist the schema marker into the restored object', () => {
    saveGuidedSession(sample())
    const restored = loadGuidedSession()
    expect(restored).not.toBeNull()
    expect('v' in (restored as object)).toBe(false)
  })
})
