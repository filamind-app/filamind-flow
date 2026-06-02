/** Guided-tuning state machine + pass/fail gates. Pure + testable. The gates DELEGATE
 *  to the existing scorers (NoiseResult.grade, beltVerdict, gradeAnalysis) — there is
 *  one definition of "pass", shared with the manual tools.
 */

import { beltVerdict } from './compare'
import { gradeAnalysis } from './grade'
import type { NoiseResult, ShaperAnalysis } from './types'

export type StepId = 'noise' | 'belts' | 'shaperX' | 'shaperY' | 'done'
export type GateStatus = 'passed' | 'warn' | 'failed'

export interface Gate {
  status: GateStatus
  headline: string
}

export interface StepDef {
  id: StepId
  label: string
  title: string
  why: string
  /** Whether running this step moves the toolhead (needs the confirm gate). */
  motion: boolean
}

export const STEPS: StepDef[] = [
  {
    id: 'noise',
    label: 'Noise',
    title: 'Accelerometer noise',
    why: 'Confirm the sensor is mounted solidly before any test (motion-free).',
    motion: false,
  },
  {
    id: 'belts',
    label: 'Belts',
    title: 'CoreXY belt balance',
    why: 'Match the two belt tensions. CoreXY only — skip on a cartesian / bed-slinger.',
    motion: true,
  },
  {
    id: 'shaperX',
    label: 'Shaper X',
    title: 'Input shaper — X',
    why: 'Find the X resonance and the best shaper.',
    motion: true,
  },
  {
    id: 'shaperY',
    label: 'Shaper Y',
    title: 'Input shaper — Y',
    why: 'Find the Y resonance and the best shaper.',
    motion: true,
  },
  { id: 'done', label: 'Done', title: 'Tuning summary', why: '', motion: false },
]

/** The next step after ``id`` (stays at 'done' at the end). */
export function nextStep(id: StepId): StepId {
  const i = STEPS.findIndex((s) => s.id === id)
  return STEPS[Math.min(i + 1, STEPS.length - 1)].id
}

export function gateNoise(noise: NoiseResult): Gate {
  if (noise.grade === 'good') return { status: 'passed', headline: 'Sensor is quiet' }
  if (noise.grade === 'elevated') return { status: 'warn', headline: 'Noise is a bit high' }
  return { status: 'failed', headline: 'Too noisy — fix the mount' }
}

export function gateBelts(a: ShaperAnalysis, b: ShaperAnalysis): Gate {
  const verdict = beltVerdict(a, b)
  if (verdict.matched) return { status: 'passed', headline: 'Belts matched' }
  if (verdict.diffPct < 25) {
    return { status: 'warn', headline: `Belts differ (Δ${verdict.diffPct.toFixed(0)}%)` }
  }
  return { status: 'failed', headline: `Belts mismatched (Δ${verdict.diffPct.toFixed(0)}%)` }
}

export function gateShaper(analysis: ShaperAnalysis): Gate {
  const grade = gradeAnalysis(analysis)
  if (grade.letter === 'A' || grade.letter === 'B') {
    return { status: 'passed', headline: `Grade ${grade.letter} — healthy axis` }
  }
  if (grade.letter === 'C') return { status: 'warn', headline: 'Grade C — usable' }
  return { status: 'failed', headline: `Grade ${grade.letter} — tune + re-test` }
}
