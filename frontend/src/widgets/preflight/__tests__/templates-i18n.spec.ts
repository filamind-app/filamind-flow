import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import PreflightWidget from '../PreflightWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Pre-Print Check renders through i18n (no leaked keys)', () => {
  it('PreflightWidget - intro + refresh + help chrome resolve, no raw key paths', () => {
    const w = mount(PreflightWidget, plugins())
    const text = w.text()
    const leaked = text.match(/preflight\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('ready') // from preflight.intro
    expect(text).toContain('Re-check') // preflight.refresh
    expect(text).toContain('Guide') // HelpDrawer trigger (preflight.help.guide)
  })
})
