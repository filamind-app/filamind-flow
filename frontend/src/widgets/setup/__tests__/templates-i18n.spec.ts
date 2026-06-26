import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import SetupWidget from '../SetupWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Setup widget renders through i18n (no leaked keys)', () => {
  it('SetupWidget - intro + chrome resolve from the bundled en catalog, no raw key paths', () => {
    const w = mount(SetupWidget, plugins())
    const text = w.text()
    // The regression this guards: en/setup.json must be merged into the eager `en` bundle, or
    // every label would render as its raw key path (setup.intro, setup.checkUpdates, …).
    const leaked = text.match(/setup\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('Install and manage') // setup.intro
    expect(text).toContain('Check for updates') // setup.checkUpdates
  })
})
