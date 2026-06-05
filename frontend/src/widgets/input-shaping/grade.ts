/** Grades the QUALITY of a resonance capture + its best shaper, so the widget can
 *  show "how good is this measurement" at a glance — a letter + score, plus a
 *  breakdown of the factors behind it. Pure + testable; derived entirely from an
 *  existing ShaperAnalysis (no extra capture needed).
 */

import { i18n } from '@/core/i18n'
import { peakSnr } from './signal'
import type { ShaperAnalysis, ShaperResult } from './types'

export type Rating = 'good' | 'ok' | 'poor'
export type Letter = 'A' | 'B' | 'C' | 'D' | 'F'

export interface QualityFactor {
  label: string
  /** Formatted measured value (e.g. "18×", "57 Hz", "1.2%"). */
  value: string
  rating: Rating
  /** Points awarded out of `max`, for the breakdown bar. */
  points: number
  max: number
  note: string
}

export interface QualityGrade {
  letter: Letter
  /** 0..100 overall score. */
  score: number
  verdict: string
  factors: QualityFactor[]
}

const FACTOR_MAX = 20

function clarityFactor(psdSum: number[]): QualityFactor {
  const ratio = peakSnr(psdSum)
  const base = { label: i18n.global.t('inputShaping.grade.clarity.label'), max: FACTOR_MAX }
  if (ratio == null)
    return {
      ...base,
      value: '—',
      rating: 'ok',
      points: 12,
      note: i18n.global.t('inputShaping.grade.clarity.note.none'),
    }
  const value = i18n.global.t('inputShaping.grade.clarity.value', { ratio: ratio.toFixed(0) })
  if (ratio >= 12)
    return {
      ...base,
      value,
      rating: 'good',
      points: 20,
      note: i18n.global.t('inputShaping.grade.clarity.note.good'),
    }
  if (ratio >= 4)
    return {
      ...base,
      value,
      rating: 'ok',
      points: 12,
      note: i18n.global.t('inputShaping.grade.clarity.note.ok'),
    }
  return {
    ...base,
    value,
    rating: 'poor',
    points: 4,
    note: i18n.global.t('inputShaping.grade.clarity.note.poor'),
  }
}

function vibrationFactor(rec: ShaperResult): QualityFactor {
  const base = { label: i18n.global.t('inputShaping.grade.vibration.label'), max: FACTOR_MAX }
  const value = i18n.global.t('inputShaping.grade.vibration.value', {
    pct: rec.vibrations_pct.toFixed(1),
  })
  if (rec.vibrations_pct <= 2)
    return {
      ...base,
      value,
      rating: 'good',
      points: 20,
      note: i18n.global.t('inputShaping.grade.vibration.note.good'),
    }
  if (rec.vibrations_pct <= 5)
    return {
      ...base,
      value,
      rating: 'ok',
      points: 13,
      note: i18n.global.t('inputShaping.grade.vibration.note.ok'),
    }
  return {
    ...base,
    value,
    rating: 'poor',
    points: 5,
    note: i18n.global.t('inputShaping.grade.vibration.note.poor'),
  }
}

function smoothingFactor(rec: ShaperResult): QualityFactor {
  const base = { label: i18n.global.t('inputShaping.grade.smoothing.label'), max: FACTOR_MAX }
  const value = rec.smoothing.toFixed(3)
  if (rec.smoothing <= 0.1)
    return {
      ...base,
      value,
      rating: 'good',
      points: 20,
      note: i18n.global.t('inputShaping.grade.smoothing.note.good'),
    }
  if (rec.smoothing <= 0.2)
    return {
      ...base,
      value,
      rating: 'ok',
      points: 12,
      note: i18n.global.t('inputShaping.grade.smoothing.note.ok'),
    }
  return {
    ...base,
    value,
    rating: 'poor',
    points: 5,
    note: i18n.global.t('inputShaping.grade.smoothing.note.poor'),
  }
}

function freqFactor(freq: number | null): QualityFactor {
  const base = { label: i18n.global.t('inputShaping.grade.freq.label'), max: FACTOR_MAX }
  if (freq == null)
    return {
      ...base,
      value: '—',
      rating: 'poor',
      points: 5,
      note: i18n.global.t('inputShaping.grade.freq.note.none'),
    }
  const value = i18n.global.t('inputShaping.grade.freq.value', { freq: freq.toFixed(0) })
  if (freq >= 40 && freq <= 90)
    return {
      ...base,
      value,
      rating: 'good',
      points: 20,
      note: i18n.global.t('inputShaping.grade.freq.note.good'),
    }
  if (freq >= 30 && freq <= 110)
    return {
      ...base,
      value,
      rating: 'ok',
      points: 12,
      note: i18n.global.t('inputShaping.grade.freq.note.ok'),
    }
  return {
    ...base,
    value,
    rating: 'poor',
    points: 5,
    note:
      freq < 30
        ? i18n.global.t('inputShaping.grade.freq.note.soft')
        : i18n.global.t('inputShaping.grade.freq.note.high'),
  }
}

function shaperFactor(name: string): QualityFactor {
  const base = { label: i18n.global.t('inputShaping.grade.shaper.label'), max: FACTOR_MAX }
  const value = name.toUpperCase()
  if (name === 'zv' || name === 'mzv')
    return {
      ...base,
      value,
      rating: 'good',
      points: 20,
      note: i18n.global.t('inputShaping.grade.shaper.note.clean'),
    }
  if (name === 'ei')
    return {
      ...base,
      value,
      rating: 'good',
      points: 16,
      note: i18n.global.t('inputShaping.grade.shaper.note.robust'),
    }
  if (name === '2hump_ei')
    return {
      ...base,
      value,
      rating: 'ok',
      points: 9,
      note: i18n.global.t('inputShaping.grade.shaper.note.twin'),
    }
  if (name === '3hump_ei')
    return {
      ...base,
      value,
      rating: 'poor',
      points: 6,
      note: i18n.global.t('inputShaping.grade.shaper.note.multiple'),
    }
  return {
    ...base,
    value,
    rating: 'ok',
    points: 12,
    note: i18n.global.t('inputShaping.grade.shaper.note.atypical'),
  }
}

function letterFor(score: number): { letter: Letter; verdict: string } {
  if (score >= 85) return { letter: 'A', verdict: i18n.global.t('inputShaping.grade.verdict.a') }
  if (score >= 70) return { letter: 'B', verdict: i18n.global.t('inputShaping.grade.verdict.b') }
  if (score >= 55) return { letter: 'C', verdict: i18n.global.t('inputShaping.grade.verdict.c') }
  if (score >= 40) return { letter: 'D', verdict: i18n.global.t('inputShaping.grade.verdict.d') }
  return { letter: 'F', verdict: i18n.global.t('inputShaping.grade.verdict.f') }
}

/** Grades a resonance analysis A–F from five equally-weighted factors. */
export function gradeAnalysis(analysis: ShaperAnalysis): QualityGrade {
  const rec = analysis.shapers.find((s) => s.recommended)
  if (!analysis.recommended_shaper || !rec) {
    return {
      letter: 'F',
      score: 0,
      verdict: i18n.global.t('inputShaping.grade.verdict.none'),
      factors: [clarityFactor(analysis.psd_sum)],
    }
  }
  const factors = [
    clarityFactor(analysis.psd_sum),
    vibrationFactor(rec),
    smoothingFactor(rec),
    freqFactor(analysis.recommended_freq),
    shaperFactor(analysis.recommended_shaper),
  ]
  const score = Math.round(factors.reduce((sum, f) => sum + f.points, 0))
  const { letter, verdict } = letterFor(score)
  return { letter, score, verdict, factors }
}
