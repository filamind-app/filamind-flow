import { afterAll, describe, expect, it } from 'vitest'

import { availableLocales, i18n, loadLocaleMessages, setLocale } from '../i18n'

const LANGS = ['ar', 'de', 'zh-Hans', 'fr', 'es', 'ru']
const t = i18n.global.t as unknown as (k: string, named?: object, plural?: number) => string

describe('all shipped locales', () => {
  it('the switcher now offers en + the 6 translations', () => {
    expect(availableLocales.map((m) => m.code).sort()).toEqual(
      ['ar', 'de', 'en', 'es', 'fr', 'ru', 'zh-Hans'].sort(),
    )
  })

  for (const lang of LANGS) {
    it(`${lang}: loads, resolves keys, and selects a plural branch`, async () => {
      await loadLocaleMessages(lang)
      i18n.global.locale.value = lang

      // Brand stays Latin in every locale.
      expect(t('common.appName')).toBe('FilaMind Flow')
      // A shell key resolves to real (non-key, non-empty) text.
      const dash = t('shell.nav.dashboard')
      expect(dash.length).toBeGreaterThan(0)
      expect(dash).not.toContain('shell.nav.dashboard')
      // Pipe-plural: a single branch is chosen (no raw '|'), with the count interpolated.
      const one = t('firmware.widget.healthIssues', { n: 1 }, 1)
      const many = t('firmware.widget.healthIssues', { n: 5 }, 5)
      expect(one).not.toContain('|')
      expect(many).not.toContain('|')
      expect(one).toContain('1')
      expect(many).toContain('5')
    })
  }

  afterAll(async () => {
    await setLocale('en')
  })
})
