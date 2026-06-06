import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import BoardTopologyWidget from '../BoardTopologyWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('Board Topology template renders through i18n (no leaked keys)', () => {
  it('BoardTopologyWidget — intro + help chrome, no raw key paths', () => {
    const w = mount(BoardTopologyWidget, plugins())
    const text = w.text()
    const leaked = text.match(/boardTopology\.[a-zA-Z]/)
    expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
    expect(text).toContain('control boards connect') // intro
    expect(text).toContain('Help') // HelpDrawer trigger
  })
})
