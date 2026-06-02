/** Maps a resonance analysis to plain-language mechanical diagnostics + fixes,
 *  each tagged with an illustration key the widget draws (DiagnosticIllo.vue).
 *  This is the "what's wrong and how to fix it, with a picture" layer. Pure +
 *  testable.
 */

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
        title: 'No usable resonance',
        advice:
          'Re-run TEST_RESONANCES. Check the accelerometer is wired and mounted firmly to the toolhead.',
        detail: 'no clear peak detected',
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
      title: 'Noisy capture',
      advice:
        'Secure the accelerometer mount and re-run. Avoid fans or other motion during the test.',
      detail: `signal-to-noise ${snr.toFixed(1)}×`,
    })
  }
  if (freq != null && freq < LOW_FREQ) {
    out.push({
      level: 'bad',
      illo: 'belt',
      title: 'Low resonance frequency',
      advice:
        'Soft or heavy axis — tighten the belts and check frame rigidity. A stiffer axis resonates higher and prints faster.',
      detail: `${freq.toFixed(1)} Hz`,
    })
  } else if (freq != null && freq < SOFT_FREQ) {
    out.push({
      level: 'warn',
      illo: 'frame',
      title: 'Somewhat soft axis',
      advice:
        'Frequency is on the low side. Firming up belts or the frame raises it and lets you print faster.',
      detail: `${freq.toFixed(1)} Hz`,
    })
  }
  if (rec.smoothing > HIGH_SMOOTHING) {
    out.push({
      level: 'warn',
      illo: 'tune',
      title: 'High smoothing',
      advice: 'Will round corners. Pick a stiffer shaper or lower max_accel.',
      detail: `smoothing ${rec.smoothing.toFixed(3)}`,
    })
  }
  if (MULTI_HUMP.includes(analysis.recommended_shaper)) {
    out.push({
      level: 'warn',
      illo: 'toolhead',
      title: 'Multiple resonances',
      advice:
        'Often a loose toolhead, belt, or part. Re-seat the toolhead and re-check belt tension.',
      detail: analysis.recommended_shaper.toUpperCase(),
    })
  }
  if (rec.vibrations_pct > HIGH_VIBR) {
    out.push({
      level: 'warn',
      illo: 'tune',
      title: 'Vibration remains',
      advice: 'Mechanical tuning (belts, frame, toolhead mass) could push this lower.',
      detail: `${rec.vibrations_pct.toFixed(1)}% left after shaping`,
    })
  }

  if (!out.length) {
    out.push({
      level: 'good',
      illo: 'ok',
      title: 'Healthy axis',
      advice: 'Clean capture and a stiff axis — good to go. Apply the config and restart Klipper.',
      detail: `${analysis.recommended_shaper.toUpperCase()} @ ${freq?.toFixed(1)} Hz`,
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
    title: 'X and Y differ a lot',
    advice:
      'Asymmetric stiffness. Check belt tension on the softer axis; on CoreXY make sure both belts are matched and tight.',
    detail: `X ${fx.toFixed(0)} Hz vs Y ${fy.toFixed(0)} Hz`,
  }
}
