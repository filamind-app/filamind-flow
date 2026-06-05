/** Turns a step's result into ranked, concrete "do this next" suggestions. A thin
 *  mapping over the EXISTING scorers (diagnose, beltVerdict, NoiseResult.grade) — no
 *  new physics. Pure + testable.
 */

import { i18n } from '@/core/i18n'

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
    return [
      {
        level: 'ok',
        title: i18n.global.t('inputShaping.recommend.noise.quiet.title'),
        why: i18n.global.t('inputShaping.recommend.noise.quiet.why'),
      },
    ]
  }
  if (noise.grade === 'elevated') {
    return [
      {
        level: 'consider',
        title: i18n.global.t('inputShaping.recommend.noise.elevated.title'),
        why: i18n.global.t('inputShaping.recommend.noise.elevated.why', {
          max: noise.max_noise.toFixed(0),
          threshold: noise.threshold,
        }),
      },
    ]
  }
  return [
    {
      level: 'do-now',
      title: i18n.global.t('inputShaping.recommend.noise.bad.title'),
      why: i18n.global.t('inputShaping.recommend.noise.bad.why', {
        max: noise.max_noise.toFixed(0),
      }),
    },
  ]
}

export function recommendBelts(verdict: BeltVerdict): Suggestion[] {
  if (verdict.matched) {
    return [
      {
        level: 'ok',
        title: i18n.global.t('inputShaping.recommend.belts.matched.title'),
        why: i18n.global.t('inputShaping.recommend.belts.matched.why'),
      },
    ]
  }
  const looser = verdict.peakA < verdict.peakB ? 'A (1,1)' : 'B (1,-1)'
  return [
    {
      level: 'do-now',
      title: i18n.global.t('inputShaping.recommend.belts.mismatch.title', { looser }),
      why: i18n.global.t('inputShaping.recommend.belts.mismatch.why', {
        peakA: verdict.peakA.toFixed(0),
        peakB: verdict.peakB.toFixed(0),
        diffPct: verdict.diffPct.toFixed(0),
      }),
    },
  ]
}

export function recommendVibrations(profile: VibrationsProfile): Suggestion[] {
  if (profile.low_freq_warning) {
    return [
      {
        level: 'do-now',
        title: i18n.global.t('inputShaping.recommend.vibrations.lowFreq.title'),
        why: i18n.global.t('inputShaping.recommend.vibrations.lowFreq.why'),
      },
    ]
  }
  const out: Suggestion[] = []
  if (profile.recommended_speed != null && profile.good_speed_ranges.length) {
    const b = profile.good_speed_ranges[0]
    out.push({
      level: 'ok',
      title: i18n.global.t('inputShaping.recommend.vibrations.favour.title', {
        speed: profile.recommended_speed.toFixed(0),
      }),
      why: i18n.global.t('inputShaping.recommend.vibrations.favour.why', {
        start: b.start.toFixed(0),
        end: b.end.toFixed(0),
      }),
    })
  }
  if (profile.peak_speeds.length) {
    const shown = profile.peak_speeds
      .slice(0, 4)
      .map((p) => p.toFixed(0))
      .join(', ')
    out.push({
      level: 'consider',
      title: i18n.global.t('inputShaping.recommend.vibrations.avoid.title', { shown }),
      why: i18n.global.t('inputShaping.recommend.vibrations.avoid.why'),
    })
  }
  if (profile.symmetry_pct < 60) {
    out.push({
      level: 'do-now',
      title: i18n.global.t('inputShaping.recommend.vibrations.symmetry.title'),
      why: i18n.global.t('inputShaping.recommend.vibrations.symmetry.why', {
        pct: profile.symmetry_pct.toFixed(0),
      }),
    })
  }
  if (!out.length) {
    out.push({
      level: 'ok',
      title: i18n.global.t('inputShaping.recommend.vibrations.fine.title'),
      why: i18n.global.t('inputShaping.recommend.vibrations.fine.why'),
    })
  }
  return out
}

export function recommendPressure(): Suggestion[] {
  return [
    {
      level: 'do-now',
      title: i18n.global.t('inputShaping.recommend.pressure.title'),
      why: i18n.global.t('inputShaping.recommend.pressure.why'),
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
