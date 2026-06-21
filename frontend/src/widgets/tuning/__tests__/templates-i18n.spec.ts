import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import TuningWidget from '../TuningWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Tuning wizards render through i18n (no leaked keys)', () => {
  it('TuningWidget - intro + PA title + help chrome resolve, no raw key paths', () => {
    const w = mount(TuningWidget, plugins())
    const text = w.text()
    const leaked = text.match(/tuning\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('calibration') // from tuning.intro
    expect(text).toContain('Pressure Advance') // tuning.pa.title
    expect(text).toContain('Guide') // HelpDrawer trigger (tuning.help.guide)
  })
})
