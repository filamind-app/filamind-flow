import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import ConfigTemplatesWidget from '../ConfigTemplatesWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Config Templates template renders through i18n (no leaked keys)', () => {
  it('ConfigTemplatesWidget — intro + filter + help, no raw key paths', () => {
    const w = mount(ConfigTemplatesWidget, plugins())
    const text = w.text()
    const leaked = text.match(/configTemplates\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('Ready-to-paste') // intro
    expect(text).toContain('Category') // filter label
    expect(text).toContain('Help') // HelpDrawer trigger
  })
})
