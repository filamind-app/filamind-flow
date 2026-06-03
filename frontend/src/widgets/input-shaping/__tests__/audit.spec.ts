import { afterEach, describe, expect, it } from 'vitest'

import {
  archiveToRecord,
  buildNoiseRecord,
  buildShaperRecord,
  buildSustainRecord,
  buildVibrationsRecord,
  loadLocalAudit,
  mergeAudit,
  migrateLegacyHistory,
  recordAudit,
  withAuditTrends,
  type AuditRecord,
} from '../audit'
import type { QualityGrade } from '../grade'
import type {
  ArchiveRun,
  NoiseResult,
  ShaperAnalysis,
  StaticExcitationResult,
  VibrationsProfile,
} from '../types'

afterEach(() => localStorage.clear())

function rec(
  over: Partial<Omit<AuditRecord, 'id' | 'source'>> = {},
): Omit<AuditRecord, 'id' | 'source'> {
  return { at: new Date().toISOString(), kind: 'noise', axis: null, fields: [], ...over }
}

describe('audit', () => {
  it('records and reads back, newest first', () => {
    recordAudit(rec({ at: '2026-06-01T00:00:00Z', kind: 'noise' }))
    recordAudit(rec({ at: '2026-06-02T00:00:00Z', kind: 'belts' }))
    const all = loadLocalAudit()
    expect(all).toHaveLength(2)
    expect(all[0].kind).toBe('belts') // most recently recorded is first
    expect(all[0].source).toBe('local')
  })

  it('caps each kind at 20 independently', () => {
    for (let i = 0; i < 25; i++) recordAudit(rec({ kind: 'shaper', at: `2026-06-01T00:00:${i}Z` }))
    recordAudit(rec({ kind: 'noise' }))
    const all = loadLocalAudit()
    expect(all.filter((r) => r.kind === 'shaper')).toHaveLength(20)
    expect(all.filter((r) => r.kind === 'noise')).toHaveLength(1)
  })

  it('migrates the legacy grade-history once, only when empty', () => {
    localStorage.setItem(
      'filamind.input-shaping.history',
      JSON.stringify([
        { at: '2026-05-01T00:00:00Z', axis: 'x', shaper: 'mzv', freq: 57, grade: 'A', score: 95 },
      ]),
    )
    migrateLegacyHistory()
    const migrated = loadLocalAudit()
    expect(migrated).toHaveLength(1)
    expect(migrated[0].kind).toBe('shaper')
    expect(migrated[0].grade).toEqual({ letter: 'A', score: 95 })
    // Idempotent: a second call (audit no longer empty) doesn't duplicate.
    migrateLegacyHistory()
    expect(loadLocalAudit()).toHaveLength(1)
  })

  it('maps an archive run to a record with summary fields', () => {
    const run: ArchiveRun = {
      id: '2026-06-03_10-00-00_config_x',
      at: '2026-06-03T10:00:00Z',
      kind: 'config',
      axis: 'x',
      summary: { shaper: 'mzv', freq: 57, verdict: 'ok' },
      files: ['input_shaper.cfg'],
      size: 42,
      config_text: null,
    }
    const r = archiveToRecord(run)
    expect(r.source).toBe('archive')
    expect(r.runId).toBe(run.id)
    expect(r.verdict).toBe('ok')
    expect(r.fields.map((f) => f.label)).toEqual(['shaper', 'freq']) // verdict excluded from fields
  })

  it('merges local + archive newest-first', () => {
    const local: AuditRecord[] = [
      {
        id: 'a',
        at: '2026-06-01T00:00:00Z',
        kind: 'shaper',
        axis: 'x',
        source: 'local',
        fields: [],
      },
    ]
    const runs: ArchiveRun[] = [
      {
        id: 'r',
        at: '2026-06-05T00:00:00Z',
        kind: 'config',
        axis: null,
        summary: {},
        files: [],
        size: 0,
        config_text: null,
      },
    ]
    const merged = mergeAudit(local, runs)
    expect(merged.map((r) => r.at)).toEqual(['2026-06-05T00:00:00Z', '2026-06-01T00:00:00Z'])
  })

  it('annotates shaper trend vs the previous same-axis run', () => {
    const records: AuditRecord[] = [
      {
        id: '2',
        at: '2026-06-02T00:00:00Z',
        kind: 'shaper',
        axis: 'x',
        source: 'local',
        grade: { letter: 'A', score: 90 },
        fields: [],
      },
      {
        id: '1',
        at: '2026-06-01T00:00:00Z',
        kind: 'shaper',
        axis: 'x',
        source: 'local',
        grade: { letter: 'B', score: 80 },
        fields: [],
      },
    ]
    expect(withAuditTrends(records)[0].trend).toBe('up') // 90 > 80
  })

  it('builds a shaper record from an analysis + grade', () => {
    const analysis = {
      recommended_shaper: 'mzv',
      recommended_freq: 57,
      axis: 'x',
      shapers: [
        {
          name: 'mzv',
          freq: 57,
          vibrations_pct: 1,
          smoothing: 0.08,
          max_accel: 7000,
          recommended: true,
        },
      ],
    } as unknown as ShaperAnalysis
    const grade = {
      letter: 'A',
      score: 95,
      verdict: 'Excellent',
      factors: [
        { label: 'Frequency', value: '57 Hz', rating: 'good', points: 20, max: 20, note: '' },
      ],
    } as unknown as QualityGrade
    const r = buildShaperRecord(analysis, grade)
    expect(r.kind).toBe('shaper')
    expect(r.grade).toEqual({ letter: 'A', score: 95 })
    expect(r.fields[0]).toEqual({ label: 'Recommended', value: 'MZV @ 57.0 Hz' })
  })

  it('builds per-property records for the live tools', () => {
    const noise = buildNoiseRecord({
      chips: [{ label: 'xy', x: 1, y: 2, z: 3 }],
      max_noise: 44.8,
      grade: 'good',
      ok: true,
      threshold: 100,
    } as NoiseResult)
    expect(noise.kind).toBe('noise')
    expect(noise.fields.find((f) => f.label === 'Status')?.value).toBe('good')

    const sustain = buildSustainRecord({
      axis: 'x',
      freq: 57,
      dominant_freq: 57.3,
      excited_band_pct: 92,
      dominant_ok: true,
      verdict: 'holding',
    } as StaticExcitationResult)
    expect(sustain.kind).toBe('static')
    expect(sustain.axis).toBe('x')

    const vib = buildVibrationsRecord({
      recommended_speed: 46,
      symmetry_pct: 100,
      motor_freq: 146,
      peak_speeds: [120],
      verdict: 'ok',
    } as VibrationsProfile)
    expect(vib.kind).toBe('vibrations')
    expect(vib.fields.find((f) => f.label === 'Symmetry')?.value).toBe('100%')
    expect(vib.fields.find((f) => f.label === 'Avoid')?.value).toContain('120')
  })
})
