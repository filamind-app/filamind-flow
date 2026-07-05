/** Shared Machine Doctor verdict/label logic, used by BOTH the widget and the home summary tile so
 *  they can never drift (a duplicated copy on the home once rendered the raw `["tuning","flow"]`
 *  array because only the widget's copy localized the `pillars` array param). */
import { useI18n } from 'vue-i18n'

import { useNav } from '@/core/nav'

import type { DoctorAssessment } from './types'

/** Deep-link target (widget id + optional tab) for each setup pillar's "Run it" action. */
const SETUP_TARGET: Record<string, { widget: string; tab?: string }> = {
  tuning: { widget: 'input-shaping', tab: 'guided' },
  flow: { widget: 'max-flow' },
  drivers: { widget: 'motor-drivers' },
}

/** A setup step's checkbox colour follows its STATUS, not merely whether it has a score - a step
 *  that was run but measured badly must not show the green "done" swatch while the hero verdict
 *  calls it broken. `ok` = run & good (lime), `warn` = run & marginal (yellow), `fail` = run & bad
 *  (red), `todo`/`unknown` = not run (blank). */
export function setupStepClass(status: string): string {
  if (status === 'ok') return 'bg-brand-lime text-ink'
  if (status === 'warn') return 'bg-brand-yellow text-ink'
  if (status === 'fail') return 'bg-brand-red text-paper'
  return 'bg-paper'
}

export function setupStepGlyph(status: string): string {
  if (status === 'ok' || status === 'warn') return '✓' // run (done); colour conveys quality
  if (status === 'fail') return '✕' // run, but the result is bad
  return '' // todo / blocked - not run
}

export function useDoctorAssessment() {
  const { t, te } = useI18n({ useScope: 'global' })
  const { go } = useNav()

  function pillarLabel(key: string): string {
    const k = `machineDoctor.pillar.${key}`
    return te(k) ? t(k) : key
  }

  /** The headline verdict with pillar key(s) resolved to localized labels. `pillar` is a single
   *  weakest-pillar key (critical/attention); `pillars` is a list of undone setup steps joined for
   *  the `setup_incomplete` verdict - the array MUST be mapped to labels, not spread raw. */
  function localizeAssessment(a: DoctorAssessment | null | undefined): string {
    if (!a) return ''
    const key = `machineDoctor.assessment.${a.code}`
    if (!te(key)) return ''
    const parts: Record<string, unknown> = { ...a.params }
    if (Array.isArray(a.params.pillars)) {
      parts.pillars = (a.params.pillars as string[])
        .map(pillarLabel)
        .join(t('machineDoctor.listSep'))
    }
    if (a.params.pillar) parts.pillar = pillarLabel(String(a.params.pillar))
    return t(key, parts)
  }

  function canRunSetup(key: string): boolean {
    return key in SETUP_TARGET
  }

  function goToSetup(key: string): void {
    const target = SETUP_TARGET[key]
    if (target) go(target.widget, target.tab)
  }

  return { pillarLabel, localizeAssessment, canRunSetup, goToSetup }
}
