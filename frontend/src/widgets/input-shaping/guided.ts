/** Guided-tuning state machine + pass/fail gates. Pure logic + i18n copy. The gates DELEGATE
 *  to the existing scorers (NoiseResult.grade, beltVerdict, gradeAnalysis) — there is one
 *  definition of "pass", shared with the manual tools. The step text (label/title/why) lives in
 *  the i18n catalog under inputShaping.guided.steps.<id>; this module keeps only the structure.
 */

import { beltVerdict } from './compare'
import { gradeAnalysis } from './grade'
import { i18n } from '@/core/i18n'

import type { NoiseResult, ShaperAnalysis, VibrationsProfile } from './types'

export type StepId = 'noise' | 'belts' | 'shaperX' | 'shaperY' | 'vibrations' | 'pressure' | 'done'
export type GateStatus = 'passed' | 'warn' | 'failed'

export interface Gate {
  status: GateStatus
  headline: string
}

export interface StepDef {
  id: StepId
  /** Whether running this step moves the toolhead (needs the confirm gate). */
  motion: boolean
  /** Manual-for-now: a self-report / instructions step, not an endpoint call. */
  manual?: boolean
}

/** Step order + structure. The label/title/why text is in inputShaping.guided.steps.<id>. */
export const STEPS: StepDef[] = [
  { id: 'noise', motion: false },
  { id: 'belts', motion: true },
  { id: 'shaperX', motion: true },
  { id: 'shaperY', motion: true },
  { id: 'vibrations', motion: true },
  { id: 'pressure', motion: false, manual: true },
  { id: 'done', motion: false },
]

/** The standard Klipper pressure-advance tuning-tower g-code. */
export const PA_TOWER_GCODE =
  'TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE START=0 FACTOR=.005'

/** The next step after ``id`` (stays at 'done' at the end). */
export function nextStep(id: StepId): StepId {
  const i = STEPS.findIndex((s) => s.id === id)
  return STEPS[Math.min(i + 1, STEPS.length - 1)].id
}

export function gateNoise(noise: NoiseResult): Gate {
  if (noise.grade === 'good')
    return { status: 'passed', headline: i18n.global.t('inputShaping.guided.gate.noise.passed') }
  if (noise.grade === 'elevated')
    return { status: 'warn', headline: i18n.global.t('inputShaping.guided.gate.noise.warn') }
  return { status: 'failed', headline: i18n.global.t('inputShaping.guided.gate.noise.failed') }
}

export function gateBelts(a: ShaperAnalysis, b: ShaperAnalysis): Gate {
  const verdict = beltVerdict(a, b)
  if (verdict.matched)
    return { status: 'passed', headline: i18n.global.t('inputShaping.guided.gate.belts.passed') }
  if (verdict.diffPct < 25) {
    return {
      status: 'warn',
      headline: i18n.global.t('inputShaping.guided.gate.belts.differ', {
        diffPct: verdict.diffPct.toFixed(0),
      }),
    }
  }
  return {
    status: 'failed',
    headline: i18n.global.t('inputShaping.guided.gate.belts.mismatched', {
      diffPct: verdict.diffPct.toFixed(0),
    }),
  }
}

export function gateShaper(analysis: ShaperAnalysis): Gate {
  const grade = gradeAnalysis(analysis)
  if (grade.letter === 'A' || grade.letter === 'B') {
    return {
      status: 'passed',
      headline: i18n.global.t('inputShaping.guided.gate.shaper.healthy', { letter: grade.letter }),
    }
  }
  if (grade.letter === 'C')
    return { status: 'warn', headline: i18n.global.t('inputShaping.guided.gate.shaper.usable') }
  return {
    status: 'failed',
    headline: i18n.global.t('inputShaping.guided.gate.shaper.tune', { letter: grade.letter }),
  }
}

export function gateVibrations(profile: VibrationsProfile): Gate {
  if (profile.low_freq_warning) {
    return {
      status: 'failed',
      headline: i18n.global.t('inputShaping.guided.gate.vibrations.lowFreq'),
    }
  }
  if (profile.symmetry_pct < 60) {
    return {
      status: 'warn',
      headline: i18n.global.t('inputShaping.guided.gate.vibrations.mismatched', {
        pct: profile.symmetry_pct.toFixed(0),
      }),
    }
  }
  const rec = profile.recommended_speed
  return {
    status: 'passed',
    headline:
      rec != null
        ? i18n.global.t('inputShaping.guided.gate.vibrations.smoothest', { rec: rec.toFixed(0) })
        : i18n.global.t('inputShaping.guided.gate.vibrations.complete'),
  }
}
