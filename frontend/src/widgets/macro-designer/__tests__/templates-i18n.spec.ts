import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import MacroDesignerWidget from '../MacroDesignerWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Macro Designer template renders through i18n (no leaked keys)', () => {
  it('MacroDesignerWidget — intro + editor + help, no raw key paths', () => {
    const w = mount(MacroDesignerWidget, plugins())
    const text = w.text()
    const leaked = text.match(/macroDesigner\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('Simulate G-code offline') // intro
    expect(text).toContain('Simulate') // editor button
    expect(text).toContain('Help') // HelpDrawer trigger
  })
})
