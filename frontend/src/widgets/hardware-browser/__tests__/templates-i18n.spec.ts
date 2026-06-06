import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import HardwareBrowserWidget from '../HardwareBrowserWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Hardware Browser template renders through i18n (no leaked keys)', () => {
  it('HardwareBrowserWidget — intro + search controls + help, no raw key paths', () => {
    const w = mount(HardwareBrowserWidget, plugins())
    const text = w.text()
    const leaked = text.match(/hardwareBrowser\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('curated reference') // intro
    expect(text).toContain('Search') // search button
    expect(text).toContain('Help') // HelpDrawer trigger
  })
})
