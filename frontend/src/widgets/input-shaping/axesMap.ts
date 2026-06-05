/** Pure helpers for the axes-map result — the paste-ready config, verdict text and
 *  Neo-Brutalist badge classes. Testable like grade.ts / diagnose.ts.
 */

import type { AxesMapResult, AxisMapping } from './types'
import { i18n } from '@/core/i18n'

/** The paste-ready printer.cfg snippet for the detected axes_map. */
export function axesMapConfig(result: AxesMapResult): string {
  return `[${result.chip}]\naxes_map: ${result.axes_map}`
}

/** Headline background class by detection status. */
export function statusBg(status: AxesMapResult['status']): string {
  if (status === 'ok') return 'bg-brand-lime'
  if (status === 'warning') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}

/** A "X → +z" arrow label for one mapping. */
export function mappingArrow(m: AxisMapping): string {
  return `${m.machine_axis.toUpperCase()} → ${m.sign}${m.accel_axis}`
}

/** Badge class for an angle-error (green ≤5°, yellow ≤15°, red else). */
export function angleClass(deg: number): string {
  if (deg <= 5) return 'bg-brand-lime'
  if (deg <= 15) return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}

/** One-line guidance vs. the currently configured axes_map. */
export function matchVerdict(result: AxesMapResult): string {
  if (result.matches_current === true)
    return i18n.global.t('inputShaping.axesMap.verdict.alreadyCorrect')
  if (result.matches_current === false)
    return i18n.global.t('inputShaping.axesMap.verdict.update', { axes_map: result.axes_map })
  return i18n.global.t('inputShaping.axesMap.verdict.add')
}
