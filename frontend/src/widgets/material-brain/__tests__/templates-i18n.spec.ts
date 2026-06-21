import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import MaterialBrainWidget from '../MaterialBrainWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Material Brain renders through i18n (no leaked keys)', () => {
  it('MaterialBrainWidget - intro + help chrome resolve, no raw key paths', () => {
    const w = mount(MaterialBrainWidget, plugins())
    const text = w.text()
    const leaked = text.match(/material\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('filament') // from material.intro
    expect(text).toContain('Guide') // HelpDrawer trigger (material.help.guide)
  })
})
