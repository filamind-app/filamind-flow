import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import KnownGoodPackWidget from '../KnownGoodPackWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Known-Good Pack renders through i18n (no leaked keys)', () => {
  it('KnownGoodPackWidget - intro + create + help chrome resolve, no raw key paths', () => {
    const w = mount(KnownGoodPackWidget, plugins())
    const text = w.text()
    const leaked = text.match(/knownGoodPack\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('config') // from knownGoodPack.intro
    expect(text).toContain('Create pack') // knownGoodPack.create.button
    expect(text).toContain('Guide') // HelpDrawer trigger
  })
})
