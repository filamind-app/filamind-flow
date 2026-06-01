/** Turns a resonance analysis into plain-language guidance — so the widget says
 *  what the numbers mean, not just shows a graph. Pure + testable.
 */

import type { ShaperAnalysis } from './types'

export interface Hint {
  level: 'good' | 'warn' | 'info'
  text: string
}

const LOW_FREQ_HZ = 30
const HIGH_SMOOTHING = 0.2
const MULTI_HUMP = ['2hump_ei', '3hump_ei']

/** Produces a short, ordered list of hints for an analysis. */
export function interpret(analysis: ShaperAnalysis): Hint[] {
  const rec = analysis.shapers.find((s) => s.recommended)
  if (!analysis.recommended_shaper || !rec) {
    return [
      {
        level: 'warn',
        text: 'No clear shaper — the data may be noisy or the axis very stiff. Re-run TEST_RESONANCES.',
      },
    ]
  }

  const hints: Hint[] = [
    {
      level: 'info',
      text: `Suggested max_accel ≤ ${rec.max_accel.toFixed(0)} mm/s² to keep smoothing low.`,
    },
  ]

  if (analysis.recommended_freq != null && analysis.recommended_freq < LOW_FREQ_HZ) {
    hints.push({
      level: 'warn',
      text: `Low shaper frequency (${analysis.recommended_freq.toFixed(1)} Hz) — a soft or heavy axis. Stiffening the frame or belts raises it and allows faster printing.`,
    })
  }
  if (rec.smoothing > HIGH_SMOOTHING) {
    hints.push({
      level: 'warn',
      text: `High smoothing (${rec.smoothing.toFixed(2)}) will round corners. A stiffer shaper or a lower max_accel reduces it.`,
    })
  }
  if (MULTI_HUMP.includes(analysis.recommended_shaper)) {
    hints.push({
      level: 'info',
      text: 'A multi-hump shaper was chosen — your axis has broad or multiple resonances.',
    })
  }
  if (rec.vibrations_pct > 5) {
    hints.push({
      level: 'info',
      text: `${rec.vibrations_pct.toFixed(1)}% vibration remains after shaping — mechanical tuning could help further.`,
    })
  }
  return hints
}
