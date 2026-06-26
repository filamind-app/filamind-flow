import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

// Deterministic backend: KlipperScreen absent — enough to render all 3 sections without any
// network. The child widgets (incl. ScreenSelector) are stubbed; this test only locks the
// 3-concern split.
vi.mock('../api', () => ({
  fetchScreenStatus: () => Promise.resolve({ present: false }),
  fetchScreenConf: vi.fn(),
  fetchScreenOptions: vi.fn(),
  fetchMenus: vi.fn(),
  fetchThemes: vi.fn(),
  saveScreenConf: vi.fn(),
  saveScreenOptions: vi.fn(),
  saveMenus: vi.fn(),
  createTheme: vi.fn(),
  activateTheme: vi.fn(),
  deleteTheme: vi.fn(),
  restartScreen: vi.fn(),
  ScreenSaveError: class ScreenSaveError extends Error {
    constructor(
      msg: string,
      public status: number,
    ) {
      super(msg)
    }
  },
}))

// The suite is unlocked (FilaMind 3D detected at runtime) → the Tools tab renders the FilaMind
// controls (the suite remote-control tab) rather than the install-required gate.
vi.mock('@/core/host/suite', async () => ({ suiteUnlocked: (await import('vue')).ref(true) }))

import ScreenManagerWidget from '../ScreenManagerWidget.vue'

const stubs = {
  ScreenSelector: true,
  FilaMindScreenTab: true,
  TouchControlPanel: true,
  HelpDrawer: true,
  HelpIllo: true,
}

function mountWidget() {
  return mount(ScreenManagerWidget, { global: { plugins: [i18n, createPinia()], stubs } })
}

describe('Screen Manager: three clean concern sections', () => {
  const label = (k: string): string => i18n.global.t('klipperscreenStudio.section.' + k) as string

  it('renders exactly the 3 concern tabs with Touch UI active by default', async () => {
    const w = mountWidget()
    await flushPromises()
    const labels = ['touch', 'klipperscreen', 'tools'].map(label)
    const tabs = w.findAll('button[aria-pressed]').filter((b) => labels.includes(b.text()))
    expect(tabs).toHaveLength(3)
    const touchTab = tabs.find((b) => b.text() === label('touch'))!
    expect(touchTab.attributes('aria-pressed')).toBe('true')
  })

  it('switching to KlipperScreen shows its (absent) state, not the touch section', async () => {
    const w = mountWidget()
    await flushPromises()
    const ksTab = w
      .findAll('button[aria-pressed]')
      .find((b) => b.text() === label('klipperscreen'))!
    await ksTab.trigger('click')
    await flushPromises()
    expect(ksTab.attributes('aria-pressed')).toBe('true')
    expect(w.text()).toContain(i18n.global.t('klipperscreenStudio.status.absent'))
  })

  it('switching to Tools leaves the KlipperScreen section and renders the tools panel', async () => {
    const w = mountWidget()
    await flushPromises()
    const toolsTab = w.findAll('button[aria-pressed]').find((b) => b.text() === label('tools'))!
    await toolsTab.trigger('click')
    await flushPromises()
    expect(toolsTab.attributes('aria-pressed')).toBe('true')
    // Left the KlipperScreen section (its absent note is gone) and the inspection-tools panel mounts.
    expect(w.text()).not.toContain(i18n.global.t('klipperscreenStudio.status.absent'))
    expect(w.findComponent({ name: 'TouchControlPanel' }).exists()).toBe(true)
  })

  it('shows the FilaMind controls in Tools when the suite is unlocked (not the install gate)', async () => {
    const w = mountWidget()
    await flushPromises()
    const toolsTab = w.findAll('button[aria-pressed]').find((b) => b.text() === label('tools'))!
    await toolsTab.trigger('click')
    await flushPromises()
    // suiteUnlocked is mocked true → the suite remote-control tab renders, gate is gone.
    expect(w.findComponent({ name: 'FilaMindScreenTab' }).exists()).toBe(true)
    expect(w.text()).not.toContain(i18n.global.t('shell.gate.title'))
  })
})
