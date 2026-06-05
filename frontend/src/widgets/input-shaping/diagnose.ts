/** Maps a resonance analysis to plain-language mechanical diagnostics + fixes,
 *  each tagged with an illustration key the widget draws (DiagnosticIllo.vue).
 *  This is the "what's wrong and how to fix it, with a picture" layer. Pure +
 *  testable.
 */

import { i18n } from '@/core/i18n'
import { peakSnr } from './signal'
import type { ShaperAnalysis } from './types'

export type DiagnosticLevel = 'good' | 'warn' | 'bad'
export type IlloKey = 'belt' | 'frame' | 'toolhead' | 'accel' | 'tune' | 'balance' | 'ok'

export interface Diagnostic {
  level: DiagnosticLevel
  illo: IlloKey
  title: string
  /** What to do about it. */
  advice: string
  /** The measured numbers behind the finding. */
  detail: string
}

const LOW_FREQ = 30
const SOFT_FREQ = 40
const HIGH_SMOOTHING = 0.2
const HIGH_VIBR = 5
const LOW_SNR = 4
const MULTI_HUMP = ['2hump_ei', '3hump_ei']
const ASYM_REL = 0.3

/** Diagnoses a single capture, newest finding first; always returns ≥1 card. */
export function diagnose(analysis: ShaperAnalysis): Diagnostic[] {
  const rec = analysis.shapers.find((s) => s.recommended)
  if (!analysis.recommended_shaper || !rec) {
    return [
      {
        level: 'bad',
        illo: 'accel',
        title: i18n.global.t('inputShaping.diagnose.noUsable.title'),
        advice: i18n.global.t('inputShaping.diagnose.noUsable.advice'),
        detail: i18n.global.t('inputShaping.diagnose.noUsable.detail'),
      },
    ]
  }

  const out: Diagnostic[] = []
  const snr = peakSnr(analysis.psd_sum)
  const freq = analysis.recommended_freq

  if (snr != null && snr < LOW_SNR) {
    out.push({
      level: 'bad',
      illo: 'accel',
      title: i18n.global.t('inputShaping.diagnose.noisy.title'),
      advice: i18n.global.t('inputShaping.diagnose.noisy.advice'),
      detail: i18n.global.t('inputShaping.diagnose.noisy.detail', { snr: snr.toFixed(1) }),
    })
  }
  if (freq != null && freq < LOW_FREQ) {
    out.push({
      level: 'bad',
      illo: 'belt',
      title: i18n.global.t('inputShaping.diagnose.lowFreq.title'),
      advice: i18n.global.t('inputShaping.diagnose.lowFreq.advice'),
      detail: i18n.global.t('inputShaping.diagnose.lowFreq.detail', { freq: freq.toFixed(1) }),
    })
  } else if (freq != null && freq < SOFT_FREQ) {
    out.push({
      level: 'warn',
      illo: 'frame',
      title: i18n.global.t('inputShaping.diagnose.softAxis.title'),
      advice: i18n.global.t('inputShaping.diagnose.softAxis.advice'),
      detail: i18n.global.t('inputShaping.diagnose.softAxis.detail', { freq: freq.toFixed(1) }),
    })
  }
  if (rec.smoothing > HIGH_SMOOTHING) {
    out.push({
      level: 'warn',
      illo: 'tune',
      title: i18n.global.t('inputShaping.diagnose.highSmoothing.title'),
      advice: i18n.global.t('inputShaping.diagnose.highSmoothing.advice'),
      detail: i18n.global.t('inputShaping.diagnose.highSmoothing.detail', {
        smoothing: rec.smoothing.toFixed(3),
      }),
    })
  }
  if (MULTI_HUMP.includes(analysis.recommended_shaper)) {
    out.push({
      level: 'warn',
      illo: 'toolhead',
      title: i18n.global.t('inputShaping.diagnose.multiResonance.title'),
      advice: i18n.global.t('inputShaping.diagnose.multiResonance.advice'),
      detail: analysis.recommended_shaper.toUpperCase(),
    })
  }
  if (rec.vibrations_pct > HIGH_VIBR) {
    out.push({
      level: 'warn',
      illo: 'tune',
      title: i18n.global.t('inputShaping.diagnose.vibrationRemains.title'),
      advice: i18n.global.t('inputShaping.diagnose.vibrationRemains.advice'),
      detail: i18n.global.t('inputShaping.diagnose.vibrationRemains.detail', {
        vibrations: rec.vibrations_pct.toFixed(1),
      }),
    })
  }

  if (!out.length) {
    out.push({
      level: 'good',
      illo: 'ok',
      title: i18n.global.t('inputShaping.diagnose.healthy.title'),
      advice: i18n.global.t('inputShaping.diagnose.healthy.advice'),
      detail: i18n.global.t('inputShaping.diagnose.healthy.detail', {
        shaper: analysis.recommended_shaper.toUpperCase(),
        freq: freq?.toFixed(1),
      }),
    })
  }
  return out
}

/** A cross-axis check: flags a big X-vs-Y stiffness mismatch (CoreXY belts, a
 *  loose gantry side, …). Returns null when both axes are close or unknown. */
export function diagnoseAxes(x: ShaperAnalysis, y: ShaperAnalysis): Diagnostic | null {
  const fx = x.recommended_freq
  const fy = y.recommended_freq
  if (fx == null || fy == null) return null
  const rel = Math.abs(fx - fy) / Math.max(fx, fy)
  if (rel < ASYM_REL) return null
  return {
    level: 'warn',
    illo: 'balance',
    title: i18n.global.t('inputShaping.diagnose.axesDiffer.title'),
    advice: i18n.global.t('inputShaping.diagnose.axesDiffer.advice'),
    detail: i18n.global.t('inputShaping.diagnose.axesDiffer.detail', {
      fx: fx.toFixed(0),
      fy: fy.toFixed(0),
    }),
  }
}
