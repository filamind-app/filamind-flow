import type { ShaperAnalysis } from './types'

/**
 * Builds a ready-to-paste Klipper `[input_shaper]` config block from one or more
 * analysed axes. An analysis with a known axis (x / y) emits axis-specific keys
 * (`shaper_type_x` / `shaper_freq_x`); one without an axis emits the generic
 * `shaper_type` / `shaper_freq`. Analyses with no recommendation are skipped.
 */
export function inputShaperConfig(analyses: ShaperAnalysis[]): string {
  const lines = ['[input_shaper]']
  for (const a of analyses) {
    if (!a.recommended_shaper || a.recommended_freq == null) continue
    const axis = (a.axis ?? '').toLowerCase()
    const suffix = axis === 'x' || axis === 'y' ? `_${axis}` : ''
    lines.push(`shaper_type${suffix}: ${a.recommended_shaper}`)
    lines.push(`shaper_freq${suffix}: ${a.recommended_freq.toFixed(1)}`)
  }
  return lines.join('\n')
}
