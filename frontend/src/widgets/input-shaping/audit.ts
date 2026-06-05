/** The Input Shaping "audit" — one aggregated, per-property record of every result
 *  (shaper analysis + the live tools: noise / belts / axes-map / sustain / vibrations),
 *  merged with the on-host archive. Browser-local (localStorage), additive: it never
 *  clears the legacy history, it folds it in once. Pure + testable; the component
 *  supplies the archive runs.
 */

import { i18n } from '@/core/i18n'
import { matchVerdict } from './axesMap'
import { beltVerdict } from './compare'
import type { QualityGrade } from './grade'
import { loadHistory } from './history'
import type {
  ArchiveRun,
  AxesMapResult,
  BeltComparison,
  NoiseResult,
  ShaperAnalysis,
  StaticExcitationResult,
  VibrationsProfile,
} from './types'

export type AuditKind =
  | 'shaper'
  | 'noise'
  | 'belts'
  | 'axes_map'
  | 'static'
  | 'vibrations'
  | 'config'
export type GradeTrend = 'up' | 'down' | 'same' | 'none'

export interface AuditField {
  label: string
  value: string
}

export interface AuditRecord {
  id: string
  /** ISO timestamp. */
  at: string
  kind: AuditKind
  axis: string | null
  /** Where the record came from: this browser, or the on-host archive. */
  source: 'local' | 'archive'
  grade?: { letter: string; score: number }
  verdict?: string
  /** The result's properties, each in its own labelled field (the "engineered" layout). */
  fields: AuditField[]
  /** For archive-backed records: the run id + its files (for download / management). */
  runId?: string
  files?: string[]
}

export interface AuditRecordWithTrend extends AuditRecord {
  trend: GradeTrend
}

const KEY = 'filamind.input-shaping.audit'
const CAP_PER_KIND = 20

function uid(at: string, kind: string): string {
  return `${at}-${kind}-${Math.random().toString(36).slice(2, 8)}`
}

/** Reads the local audit records (newest-first), tolerating missing/corrupt storage. */
export function loadLocalAudit(): AuditRecord[] {
  try {
    const raw = localStorage.getItem(KEY)
    const data = raw ? JSON.parse(raw) : []
    return Array.isArray(data) ? (data as AuditRecord[]) : []
  } catch {
    return []
  }
}

function save(records: AuditRecord[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(records))
  } catch {
    /* storage unavailable (private mode / quota) — keep the in-memory list */
  }
}

/** Keeps the newest CAP_PER_KIND records of each kind (records are newest-first). */
function capPerKind(records: AuditRecord[]): AuditRecord[] {
  const seen: Record<string, number> = {}
  return records.filter((r) => {
    const n = (seen[r.kind] = (seen[r.kind] ?? 0) + 1)
    return n <= CAP_PER_KIND
  })
}

/** Prepends a record, caps per kind, persists, returns the new local list. */
export function recordAudit(record: Omit<AuditRecord, 'id' | 'source'>): AuditRecord[] {
  const full: AuditRecord = { ...record, id: uid(record.at, record.kind), source: 'local' }
  const next = capPerKind([full, ...loadLocalAudit()])
  save(next)
  return next
}

/** Builds a shaper audit record from an analysis + its grade (fields = the factor breakdown). */
export function buildShaperRecord(
  analysis: ShaperAnalysis,
  grade: QualityGrade,
): Omit<AuditRecord, 'id' | 'source'> {
  const rec = analysis.shapers.find((s) => s.recommended)
  const fields: AuditField[] = grade.factors.map((f) => ({ label: f.label, value: f.value }))
  if (analysis.recommended_shaper && analysis.recommended_freq != null) {
    fields.unshift({
      label: i18n.global.t('inputShaping.audit.recommended'),
      value: i18n.global.t('inputShaping.audit.recommendedValue', {
        shaper: analysis.recommended_shaper.toUpperCase(),
        freq: analysis.recommended_freq.toFixed(1),
      }),
    })
  }
  if (rec)
    fields.push({
      label: i18n.global.t('inputShaping.audit.maxAccel'),
      value: i18n.global.t('inputShaping.audit.maxAccelValue', { accel: rec.max_accel.toFixed(0) }),
    })
  return {
    at: new Date().toISOString(),
    kind: 'shaper',
    axis: analysis.axis,
    grade: { letter: grade.letter, score: grade.score },
    verdict: grade.verdict,
    fields,
  }
}

function now(): string {
  return new Date().toISOString()
}

/** Audit record for an accelerometer noise check. */
export function buildNoiseRecord(n: NoiseResult): Omit<AuditRecord, 'id' | 'source'> {
  return {
    at: now(),
    kind: 'noise',
    axis: null,
    verdict: i18n.global.t('inputShaping.audit.noise.verdict', {
      max: n.max_noise.toFixed(0),
      threshold: n.threshold,
    }),
    fields: [
      { label: i18n.global.t('inputShaping.audit.noise.status'), value: n.grade },
      { label: i18n.global.t('inputShaping.audit.noise.maxNoise'), value: n.max_noise.toFixed(1) },
      { label: i18n.global.t('inputShaping.audit.noise.threshold'), value: String(n.threshold) },
      ...n.chips.map((c) => ({
        label: c.label,
        value: i18n.global.t('inputShaping.audit.noise.chipValue', {
          x: c.x.toFixed(0),
          y: c.y.toFixed(0),
          z: c.z.toFixed(0),
        }),
      })),
    ],
  }
}

/** Audit record for a CoreXY belt comparison. */
export function buildBeltsRecord(b: BeltComparison): Omit<AuditRecord, 'id' | 'source'> {
  const v = beltVerdict(b.belt_a, b.belt_b)
  return {
    at: now(),
    kind: 'belts',
    axis: null,
    verdict: v.advice,
    fields: [
      {
        label: i18n.global.t('inputShaping.audit.belts.match'),
        value: v.matched
          ? i18n.global.t('inputShaping.audit.belts.matched')
          : i18n.global.t('inputShaping.audit.belts.mismatch'),
      },
      {
        label: i18n.global.t('inputShaping.audit.belts.beltA'),
        value: i18n.global.t('inputShaping.audit.belts.hz', { value: v.peakA.toFixed(1) }),
      },
      {
        label: i18n.global.t('inputShaping.audit.belts.beltB'),
        value: i18n.global.t('inputShaping.audit.belts.hz', { value: v.peakB.toFixed(1) }),
      },
      {
        label: i18n.global.t('inputShaping.audit.belts.difference'),
        value: i18n.global.t('inputShaping.audit.belts.pct', { value: v.diffPct.toFixed(0) }),
      },
    ],
  }
}

/** Audit record for an axes-map detection. */
export function buildAxesMapRecord(a: AxesMapResult): Omit<AuditRecord, 'id' | 'source'> {
  return {
    at: now(),
    kind: 'axes_map',
    axis: null,
    verdict: matchVerdict(a),
    fields: [
      { label: i18n.global.t('inputShaping.audit.axesMap.axesMap'), value: a.axes_map },
      { label: i18n.global.t('inputShaping.audit.axesMap.status'), value: a.status },
      {
        label: i18n.global.t('inputShaping.audit.axesMap.gravity'),
        value: i18n.global.t('inputShaping.audit.axesMap.gravityValue', {
          gravity: a.gravity.toFixed(2),
        }),
      },
      { label: i18n.global.t('inputShaping.audit.axesMap.noise'), value: a.noise.toFixed(0) },
    ],
  }
}

/** Audit record for a sustain-frequency hold. */
export function buildSustainRecord(s: StaticExcitationResult): Omit<AuditRecord, 'id' | 'source'> {
  return {
    at: now(),
    kind: 'static',
    axis: s.axis,
    verdict: s.verdict,
    fields: [
      {
        label: i18n.global.t('inputShaping.audit.sustain.target'),
        value: i18n.global.t('inputShaping.audit.sustain.hz', { value: s.freq.toFixed(0) }),
      },
      {
        label: i18n.global.t('inputShaping.audit.sustain.dominant'),
        value: i18n.global.t('inputShaping.audit.sustain.hz', {
          value: s.dominant_freq.toFixed(0),
        }),
      },
      {
        label: i18n.global.t('inputShaping.audit.sustain.inBand'),
        value: i18n.global.t('inputShaping.audit.sustain.pct', {
          value: s.excited_band_pct.toFixed(0),
        }),
      },
      {
        label: i18n.global.t('inputShaping.audit.sustain.onTarget'),
        value: s.dominant_ok
          ? i18n.global.t('inputShaping.audit.sustain.yes')
          : i18n.global.t('inputShaping.audit.sustain.no'),
      },
    ],
  }
}

/** Audit record for a vibrations profile. */
export function buildVibrationsRecord(v: VibrationsProfile): Omit<AuditRecord, 'id' | 'source'> {
  const fields: AuditField[] = []
  if (v.recommended_speed != null)
    fields.push({
      label: i18n.global.t('inputShaping.audit.vibrations.smoothest'),
      value: i18n.global.t('inputShaping.audit.vibrations.mmps', {
        speed: v.recommended_speed.toFixed(0),
      }),
    })
  fields.push({
    label: i18n.global.t('inputShaping.audit.vibrations.symmetry'),
    value: i18n.global.t('inputShaping.audit.vibrations.pct', { pct: v.symmetry_pct.toFixed(0) }),
  })
  if (v.motor_freq != null)
    fields.push({
      label: i18n.global.t('inputShaping.audit.vibrations.motorResonance'),
      value: i18n.global.t('inputShaping.audit.vibrations.hz', { freq: v.motor_freq.toFixed(0) }),
    })
  if (v.peak_speeds.length)
    fields.push({
      label: i18n.global.t('inputShaping.audit.vibrations.avoid'),
      value: i18n.global.t('inputShaping.audit.vibrations.mmps', {
        speed: v.peak_speeds
          .slice(0, 4)
          .map((p) => p.toFixed(0))
          .join(', '),
      }),
    })
  return { at: now(), kind: 'vibrations', axis: null, verdict: v.verdict, fields }
}

/** One-time fold of the legacy grade-history into shaper records (only if audit is empty). */
export function migrateLegacyHistory(): void {
  if (loadLocalAudit().length) return
  const legacy = loadHistory()
  if (!legacy.length) return
  const records: AuditRecord[] = legacy.map((h) => ({
    id: `${h.at}-shaper`,
    at: h.at,
    kind: 'shaper',
    axis: h.axis,
    source: 'local',
    grade: h.grade && h.score != null ? { letter: h.grade, score: h.score } : undefined,
    fields: [
      {
        label: i18n.global.t('inputShaping.audit.recommended'),
        value: i18n.global.t('inputShaping.audit.recommendedValue', {
          shaper: h.shaper.toUpperCase(),
          freq: h.freq.toFixed(1),
        }),
      },
    ],
  }))
  save(capPerKind(records))
}

/** Maps an on-host archive run to an audit record (its summary becomes the fields). */
export function archiveToRecord(run: ArchiveRun): AuditRecord {
  const summary = run.summary ?? {}
  const fields: AuditField[] = Object.entries(summary)
    .filter(([k]) => k !== 'verdict' && k !== 'grade' && k !== 'score')
    .map(([k, v]) => ({ label: k, value: String(v) }))
  const grade =
    typeof summary.grade === 'string' && typeof summary.score === 'number'
      ? { letter: summary.grade, score: summary.score }
      : undefined
  return {
    id: `archive-${run.id}`,
    at: run.at,
    kind: (run.kind as AuditKind) ?? 'config',
    axis: run.axis,
    source: 'archive',
    grade,
    verdict: typeof summary.verdict === 'string' ? summary.verdict : undefined,
    fields,
    runId: run.id,
    files: run.files,
  }
}

/** Merges the local records with the archive runs into one newest-first list. */
export function mergeAudit(local: AuditRecord[], archiveRuns: ArchiveRun[]): AuditRecord[] {
  const all = [...local, ...archiveRuns.map(archiveToRecord)]
  return all.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
}

/** Annotates shaper records with how their score compares to the previous same-axis run. */
export function withAuditTrends(records: AuditRecord[]): AuditRecordWithTrend[] {
  return records.map((record, i) => {
    if (record.kind !== 'shaper' || record.grade == null) return { ...record, trend: 'none' }
    const prev = records
      .slice(i + 1)
      .find((p) => p.kind === 'shaper' && p.axis === record.axis && p.grade != null)
    if (!prev?.grade) return { ...record, trend: 'none' }
    if (record.grade.score > prev.grade.score) return { ...record, trend: 'up' }
    if (record.grade.score < prev.grade.score) return { ...record, trend: 'down' }
    return { ...record, trend: 'same' }
  })
}
