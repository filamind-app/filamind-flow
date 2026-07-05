import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import type { DoctorAssessment } from '../types'
import { setupStepClass, setupStepGlyph, useDoctorAssessment } from '../useDoctorAssessment'

/** Render `localizeAssessment` inside a real component so `useI18n` resolves against the global
 *  (en) messages - guards the home-page bug where the `setup_incomplete` `pillars` ARRAY leaked as
 *  the raw `["tuning","flow"]` because a copy of this logic never localized it. */
function localize(assessment: DoctorAssessment): string {
  let out = ''
  const Harness = defineComponent({
    setup() {
      out = useDoctorAssessment().localizeAssessment(assessment)
      return () => h('div', out)
    },
  })
  mount(Harness, { global: { plugins: [i18n] } })
  return out
}

describe('useDoctorAssessment', () => {
  it('localizes the setup_incomplete pillars array to labels, never the raw keys', () => {
    const text = localize({
      code: 'setup_incomplete',
      params: { grade: 'C', pillars: ['tuning', 'flow', 'drivers'] },
    })
    expect(text).toContain('Input shaping')
    expect(text).toContain('Max flow')
    expect(text).toContain('Motor drivers')
    // the bug: a raw JS array / untranslated keys must never reach the UI.
    expect(text).not.toContain('[')
    expect(text).not.toContain('tuning')
    expect(text).not.toContain('"')
  })

  it('localizes the single weakest-pillar param for the critical verdict', () => {
    const text = localize({ code: 'critical', params: { grade: 'D', pillar: 'services' } })
    expect(text).toContain('Services')
    expect(text).not.toContain('services') // the raw key, not the label
  })

  it('returns empty string for a missing assessment', () => {
    expect(localize(null as unknown as DoctorAssessment)).toBe('')
  })
})

describe('setup step swatch follows status, not score presence', () => {
  // A run-but-bad setup pillar (e.g. max flow measured 40 → status 'fail') must NOT render the
  // green "done" swatch the hero simultaneously calls broken - the swatch tracks status.
  it('a failing (run-but-bad) step is red with a ✕, never green with a ✓', () => {
    expect(setupStepClass('fail')).toContain('bg-brand-red')
    expect(setupStepGlyph('fail')).toBe('✕')
    expect(setupStepClass('fail')).not.toContain('bg-brand-lime')
  })

  it('a good step is lime with a ✓', () => {
    expect(setupStepClass('ok')).toContain('bg-brand-lime')
    expect(setupStepGlyph('ok')).toBe('✓')
  })

  it('a not-run step (todo / blocked) has a blank swatch', () => {
    expect(setupStepGlyph('todo')).toBe('')
    expect(setupStepGlyph('unknown')).toBe('')
    expect(setupStepClass('todo')).toBe('bg-paper')
  })
})
