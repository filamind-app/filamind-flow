/** Turns a step's result into ranked, concrete "do this next" suggestions. A thin
 *  mapping over the EXISTING scorers (diagnose, beltVerdict, NoiseResult.grade) — no
 *  new physics. Pure + testable.
 */

import type { BeltVerdict } from './compare'
import { diagnose } from './diagnose'
import type { NoiseResult, ShaperAnalysis } from './types'

export type SuggestionLevel = 'do-now' | 'consider' | 'ok'

export interface Suggestion {
  level: SuggestionLevel
  title: string
  why: string
}

export function recommendNoise(noise: NoiseResult): Suggestion[] {
  if (noise.grade === 'good') {
    return [{ level: 'ok', title: 'Sensor is quiet', why: 'Good to continue.' }]
  }
  if (noise.grade === 'elevated') {
    return [
      {
        level: 'consider',
        title: 'Reduce sensor noise',
        why: `Max ${noise.max_noise.toFixed(0)} ≥ ${noise.threshold}. Turn off the toolhead fan and re-check the mount, then re-run.`,
      },
    ]
  }
  return [
    {
      level: 'do-now',
      title: 'Fix the accelerometer before testing',
      why: `Noise ${noise.max_noise.toFixed(0)} is too high — re-seat the sensor and check its wiring.`,
    },
  ]
}

export function recommendBelts(verdict: BeltVerdict): Suggestion[] {
  if (verdict.matched) {
    return [
      { level: 'ok', title: 'Belts balanced', why: 'Tension is even — calibrate the shaper next.' },
    ]
  }
  const looser = verdict.peakA < verdict.peakB ? 'A (1,1)' : 'B (1,-1)'
  return [
    {
      level: 'do-now',
      title: `Re-tension belt ${looser}`,
      why: `A ${verdict.peakA.toFixed(0)} Hz vs B ${verdict.peakB.toFixed(0)} Hz (Δ${verdict.diffPct.toFixed(0)}%). Tighten the lower-frequency belt until both peaks line up, then re-run.`,
    },
  ]
}

/** Reuses the shaper diagnostics, ranked do-now (bad) → consider (warn) → ok. */
export function recommendShaper(analysis: ShaperAnalysis): Suggestion[] {
  const order: Record<string, number> = { bad: 0, warn: 1, good: 2 }
  return diagnose(analysis)
    .slice()
    .sort((a, b) => order[a.level] - order[b.level])
    .map((d) => ({
      level: d.level === 'good' ? 'ok' : d.level === 'warn' ? 'consider' : 'do-now',
      title: d.title,
      why: d.advice,
    }))
}
