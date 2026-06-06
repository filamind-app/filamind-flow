import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import ConfigEditorWidget from '../ConfigEditorWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Config Editor template renders through i18n (no leaked keys)', () => {
  it('ConfigEditorWidget — intro + help chrome, no raw key paths', () => {
    const w = mount(ConfigEditorWidget, plugins())
    const text = w.text()
    const leaked = text.match(/configEditor\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('Read your printer') // intro is always rendered
    expect(text).toContain('Help') // HelpDrawer trigger label
  })
})
