/** Turns a step's result into ranked, concrete "do this next" suggestions. A thin
 *  mapping over the EXISTING scorers (diagnose, beltVerdict, NoiseResult.grade) — no
 *  new physics. Pure + testable.
 */

import type { BeltVerdict } from './compare'
import { diagnose } from './diagnose'
import type { NoiseResult, ShaperAnalysis, VibrationsProfile } from './types'

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

export function recommendVibrations(profile: VibrationsProfile): Suggestion[] {
  if (profile.low_freq_warning) {
    return [
      {
        level: 'do-now',
        title: 'Re-run at a lower acceleration',
        why: 'Too much low-frequency motion was recorded — lower ACCEL (or raise SIZE) so only constant speeds are measured, then re-run.',
      },
    ]
  }
  const out: Suggestion[] = []
  if (profile.recommended_speed != null && profile.good_speed_ranges.length) {
    const b = profile.good_speed_ranges[0]
    out.push({
      level: 'ok',
      title: `Favour ~${profile.recommended_speed.toFixed(0)} mm/s`,
      why: `Smoothest band ${b.start.toFixed(0)}–${b.end.toFixed(0)} mm/s — set slicer print / travel speeds here when you can.`,
    })
  }
  if (profile.peak_speeds.length) {
    const shown = profile.peak_speeds
      .slice(0, 4)
      .map((p) => p.toFixed(0))
      .join(', ')
    out.push({
      level: 'consider',
      title: `Avoid ${shown} mm/s`,
      why: 'These speeds hit a resonance — keep print + travel moves away from them in the slicer.',
    })
  }
  if (profile.symmetry_pct < 60) {
    out.push({
      level: 'do-now',
      title: 'Check belt tension / motor match',
      why: `Motor symmetry ${profile.symmetry_pct.toFixed(0)}% is low — re-tension the belts (compare belts) and verify both motor currents match.`,
    })
  }
  if (!out.length) {
    out.push({ level: 'ok', title: 'Vibrations look fine', why: 'No problem speeds stood out.' })
  }
  return out
}

export function recommendPressure(): Suggestion[] {
  return [
    {
      level: 'do-now',
      title: 'Run a pressure-advance tower',
      why: 'Print the PA tower, read the height where corners look sharpest, then `SET_PRESSURE_ADVANCE ADVANCE=<value>` and `SAVE_CONFIG`.',
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
