/** Grades the QUALITY of a resonance capture + its best shaper, so the widget can
 *  show "how good is this measurement" at a glance — a letter + score, plus a
 *  breakdown of the factors behind it. Pure + testable; derived entirely from an
 *  existing ShaperAnalysis (no extra capture needed).
 */

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
  const base = { label: 'Peak clarity', max: FACTOR_MAX }
  if (ratio == null)
    return { ...base, value: '—', rating: 'ok', points: 12, note: 'No spectrum to assess.' }
  const value = `${ratio.toFixed(0)}×`
  if (ratio >= 12)
    return { ...base, value, rating: 'good', points: 20, note: 'Sharp peak, well above the noise.' }
  if (ratio >= 4)
    return { ...base, value, rating: 'ok', points: 12, note: 'Peak visible above the noise.' }
  return { ...base, value, rating: 'poor', points: 4, note: 'Weak peak — noisy or very stiff.' }
}

function vibrationFactor(rec: ShaperResult): QualityFactor {
  const base = { label: 'Residual vibration', max: FACTOR_MAX }
  const value = `${rec.vibrations_pct.toFixed(1)}%`
  if (rec.vibrations_pct <= 2)
    return { ...base, value, rating: 'good', points: 20, note: 'Almost all resonance removed.' }
  if (rec.vibrations_pct <= 5)
    return { ...base, value, rating: 'ok', points: 13, note: 'Most resonance removed.' }
  return { ...base, value, rating: 'poor', points: 5, note: 'Significant vibration remains.' }
}

function smoothingFactor(rec: ShaperResult): QualityFactor {
  const base = { label: 'Smoothing', max: FACTOR_MAX }
  const value = rec.smoothing.toFixed(3)
  if (rec.smoothing <= 0.1)
    return { ...base, value, rating: 'good', points: 20, note: 'Minimal corner rounding.' }
  if (rec.smoothing <= 0.2)
    return { ...base, value, rating: 'ok', points: 12, note: 'Some rounding at high accel.' }
  return { ...base, value, rating: 'poor', points: 5, note: 'Heavy smoothing — rounds corners.' }
}

function freqFactor(freq: number | null): QualityFactor {
  const base = { label: 'Frequency', max: FACTOR_MAX }
  if (freq == null)
    return { ...base, value: '—', rating: 'poor', points: 5, note: 'No frequency found.' }
  const value = `${freq.toFixed(0)} Hz`
  if (freq >= 40 && freq <= 90)
    return { ...base, value, rating: 'good', points: 20, note: 'Healthy, stiff axis.' }
  if (freq >= 30 && freq <= 110)
    return { ...base, value, rating: 'ok', points: 12, note: 'A little soft or very stiff.' }
  return {
    ...base,
    value,
    rating: 'poor',
    points: 5,
    note: freq < 30 ? 'Soft / heavy axis.' : 'Unusually high.',
  }
}

function shaperFactor(name: string): QualityFactor {
  const base = { label: 'Resonance shape', max: FACTOR_MAX }
  const value = name.toUpperCase()
  if (name === 'zv' || name === 'mzv')
    return { ...base, value, rating: 'good', points: 20, note: 'Clean single resonance.' }
  if (name === 'ei')
    return { ...base, value, rating: 'good', points: 16, note: 'Single resonance, robust shaper.' }
  if (name === '2hump_ei')
    return { ...base, value, rating: 'ok', points: 9, note: 'Broad or twin resonance.' }
  if (name === '3hump_ei')
    return { ...base, value, rating: 'poor', points: 6, note: 'Multiple resonances.' }
  return { ...base, value, rating: 'ok', points: 12, note: 'Atypical shaper.' }
}

function letterFor(score: number): { letter: Letter; verdict: string } {
  if (score >= 85) return { letter: 'A', verdict: 'Excellent — clean capture, well-tuned axis.' }
  if (score >= 70) return { letter: 'B', verdict: 'Good — solid result, minor room to improve.' }
  if (score >= 55) return { letter: 'C', verdict: 'Fair — usable; see the suggestions below.' }
  if (score >= 40) return { letter: 'D', verdict: 'Poor — mechanical tuning + a re-test advised.' }
  return { letter: 'F', verdict: 'Unreliable — re-run the test (check the sensor mount).' }
}

/** Grades a resonance analysis A–F from five equally-weighted factors. */
export function gradeAnalysis(analysis: ShaperAnalysis): QualityGrade {
  const rec = analysis.shapers.find((s) => s.recommended)
  if (!analysis.recommended_shaper || !rec) {
    return {
      letter: 'F',
      score: 0,
      verdict: 'No usable result — re-run TEST_RESONANCES.',
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
