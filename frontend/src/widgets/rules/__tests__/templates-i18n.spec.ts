import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import RulesWidget from '../RulesWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Rules widget renders through i18n (no leaked keys)', () => {
  it('RulesWidget - intro + engine + help chrome resolve, no raw key paths', () => {
    const w = mount(RulesWidget, plugins())
    const text = w.text()
    const leaked = text.match(/rules\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('IF-THEN') // from rules.intro
    expect(text).toContain('Add a rule') // rules.form.add
    expect(text).toContain('Guide') // HelpDrawer trigger
  })
})
