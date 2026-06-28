import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

/** The lint findings render via `configEditor.lint.rule.<rule>` with ICU placeholders filled from
 *  each finding's section + detail. Verify the placeholders resolve (no leftover braces). */
describe('Config Editor: lint rule i18n', () => {
  const t = i18n.global.t

  it('interpolates pin-conflict and heater-range findings', () => {
    const dbl = t('configEditor.lint.rule.double_assigned_pin', {
      pin: 'PA1',
      sections: 'stepper_x, fan',
    })
    expect(dbl).toContain('PA1')
    expect(dbl).toContain('stepper_x, fan')
    expect(dbl).not.toContain('{')

    const heat = t('configEditor.lint.rule.heater_temp_range', {
      section: 'extruder',
      min_temp: 250,
      max_temp: 200,
    })
    expect(heat).toContain('extruder')
    expect(heat).toContain('250')
    expect(heat).toContain('200')
    expect(heat).not.toContain('{')
  })

  it('has every lint rule key + the panel name', () => {
    const rules = [
      'double_assigned_pin',
      'pin_caveat',
      'klipper_warning',
      'save_config_pending',
      'missing_printer',
      'no_stepper',
      'heater_temp_range',
    ]
    for (const r of rules) expect(i18n.global.te('configEditor.lint.rule.' + r)).toBe(true)
    expect(i18n.global.te('configEditor.panels.name.lint')).toBe(true)
    expect(t('configEditor.lint.title', { n: 3 })).toContain('3')
  })
})
