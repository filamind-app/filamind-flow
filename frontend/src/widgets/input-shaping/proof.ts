/** Proof of tune — an honest before/after comparison built from two recorded shaper
 *  results on the same axis. Pure + testable; the component supplies the audit records
 *  (local + archive, the same merged list the Audit tab shows).
 *
 *  Only records that carry real numbers participate: a measurement grade and/or the
 *  recommended shaper's metrics. Nothing is interpolated — a missing metric renders
 *  as a dash on that row.
 */

import type { AuditRecord } from './audit'
import type { ProofMetrics } from './types'

export interface ProofRow {
  /** i18n key suffix under inputShaping.proof.metric.* */
  key: 'score' | 'vibrations' | 'smoothing' | 'maxAccel' | 'freq' | 'shaper'
  before: string
  after: string
  /** Signed delta text ('' when either side is missing or the row is non-numeric). */
  delta: string
  /** true = improved, false = regressed, null = neutral/unknown. */
  better: boolean | null
}

/** Records eligible as a before/after side: a shaper/config result on the wanted axis
 *  carrying a grade or metrics, newest-first (same order the audit list shows). */
export function proofCandidates(records: AuditRecord[], axis: string): AuditRecord[] {
  return records.filter(
    (r) =>
      (r.kind === 'shaper' || r.kind === 'config') &&
      r.axis === axis &&
      (r.grade != null || r.metrics != null),
  )
}

function fmt(v: number | null | undefined, digits = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

function deltaOf(
  before: number | null | undefined,
  after: number | null | undefined,
  digits: number,
  lowerIsBetter: boolean,
): { delta: string; better: boolean | null } {
  if (
    typeof before !== 'number' ||
    typeof after !== 'number' ||
    !Number.isFinite(before) ||
    !Number.isFinite(after)
  )
    return { delta: '', better: null }
  const d = after - before
  if (Math.abs(d) < 10 ** -digits / 2) return { delta: '±0', better: null }
  const sign = d > 0 ? '+' : '−'
  const text = `${sign}${Math.abs(d).toFixed(digits)}`
  return { delta: text, better: lowerIsBetter ? d < 0 : d > 0 }
}

function metricsOf(r: AuditRecord): ProofMetrics {
  return r.metrics ?? {}
}

/** The comparison table — score + the recommended shaper's metrics, row per metric. */
export function buildProofRows(before: AuditRecord, after: AuditRecord): ProofRow[] {
  const mb = metricsOf(before)
  const ma = metricsOf(after)
  const rows: ProofRow[] = []

  const score = deltaOf(before.grade?.score, after.grade?.score, 0, false)
  rows.push({
    key: 'score',
    before: before.grade ? `${before.grade.letter} (${before.grade.score})` : '—',
    after: after.grade ? `${after.grade.letter} (${after.grade.score})` : '—',
    ...score,
  })

  const vib = deltaOf(mb.vibrations_pct, ma.vibrations_pct, 1, true)
  rows.push({
    key: 'vibrations',
    before: fmt(mb.vibrations_pct),
    after: fmt(ma.vibrations_pct),
    ...vib,
  })

  const smoothing = deltaOf(mb.smoothing, ma.smoothing, 3, true)
  rows.push({
    key: 'smoothing',
    before: fmt(mb.smoothing, 3),
    after: fmt(ma.smoothing, 3),
    ...smoothing,
  })

  const accel = deltaOf(mb.max_accel, ma.max_accel, 0, false)
  rows.push({
    key: 'maxAccel',
    before: fmt(mb.max_accel, 0),
    after: fmt(ma.max_accel, 0),
    ...accel,
  })

  const freq = deltaOf(mb.freq, ma.freq, 1, false)
  rows.push({
    key: 'freq',
    before: fmt(mb.freq),
    after: fmt(ma.freq),
    delta: freq.delta,
    better: null, // a frequency shift is information, not improvement
  })

  rows.push({
    key: 'shaper',
    before: mb.shaper ? mb.shaper.toUpperCase() : '—',
    after: ma.shaper ? ma.shaper.toUpperCase() : '—',
    delta: '',
    better: null,
  })

  return rows
}

/** A plain-text report (for pasting into a forum / sharing). Labels are supplied
 *  pre-translated by the component. */
export function proofText(
  title: string,
  axis: string,
  beforeAt: string,
  afterAt: string,
  rows: { label: string; row: ProofRow }[],
): string {
  const lines = [title, `axis ${axis.toUpperCase()} · ${beforeAt} → ${afterAt}`]
  for (const { label, row } of rows) {
    const delta = row.delta ? ` (${row.delta})` : ''
    lines.push(`${label}: ${row.before} → ${row.after}${delta}`)
  }
  return lines.join('\n')
}
