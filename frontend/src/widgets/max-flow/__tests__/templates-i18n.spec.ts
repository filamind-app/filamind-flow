import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import MaxFlowWidget from '../MaxFlowWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Max-Flow template renders through i18n (no leaked keys)', () => {
  it('MaxFlowWidget — intro + help chrome + safety items, no raw key paths', () => {
    const w = mount(MaxFlowWidget, plugins())
    const text = w.text()
    const leaked = text.match(/maxFlow\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('Find the highest volumetric flow') // intro
    expect(text).toContain('Help') // HelpDrawer trigger
  })
})
