import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

// Deterministic catalog + status so we can assert the Update button gating and version display
// without a backend. klipper is behind (update available), moonraker is up to date, guppyscreen is
// not installed but has a known latest version.
vi.mock('../api', () => ({
  fetchCatalog: () =>
    Promise.resolve({
      schema: 1,
      groups: [
        {
          group: 'core',
          components: [
            {
              id: 'klipper',
              name: 'Klipper',
              kind: 'firmware-host',
              repo: 'k/k',
              type: 'git_repo',
            },
            {
              id: 'moonraker',
              name: 'Moonraker',
              kind: 'api-server',
              repo: 'a/m',
              type: 'git_repo',
            },
            {
              id: 'guppyscreen',
              name: 'Guppyscreen',
              kind: 'touch',
              repo: 'b/g',
              type: 'git_repo',
            },
          ],
        },
      ],
    }),
  fetchStatus: () =>
    Promise.resolve({
      status: {
        klipper: {
          status: 'installed',
          version: 'v0.13.0-689',
          latest: 'v0.13.0-699',
          updateAvailable: true,
        },
        moonraker: {
          status: 'installed',
          version: 'v0.10.0-29',
          latest: 'v0.10.0-29',
          updateAvailable: false,
        },
        guppyscreen: {
          status: 'not-installed',
          version: '',
          latest: 'v0.0.26',
          updateAvailable: false,
        },
      },
      writesEnabled: true,
      suiteCommand: 'curl -fsSL example | bash',
    }),
  installComponent: vi.fn(),
  installComponentStream: vi.fn(),
  updateComponent: vi.fn(),
  removeComponent: vi.fn(),
  setPort: vi.fn(),
  setWrites: vi.fn(),
}))

import SetupWidget from '../SetupWidget.vue'

function mountWidget() {
  return mount(SetupWidget, { global: { plugins: [i18n, createPinia()] } })
}

describe('Setup widget: versions + smart Update button', () => {
  it('shows Update only for a component that is behind, never for an up-to-date one', async () => {
    const w = mountWidget()
    await flushPromises()

    const update = i18n.global.t('setup.update') as string
    const upToDate = i18n.global.t('setup.upToDate') as string

    // Exactly one Update button — for klipper (behind), not moonraker (current) nor the
    // not-installed component (which offers Install, not Update).
    const updateButtons = w.findAll('button').filter((b) => b.text() === update)
    expect(updateButtons).toHaveLength(1)

    // The up-to-date installed component shows an "up to date" hint instead of an Update button.
    expect(w.text()).toContain(upToDate)
  })

  it('reads version numbers for installed and not-installed components', async () => {
    const w = mountWidget()
    await flushPromises()
    const text = w.text()
    expect(text).toContain('v0.13.0-689') // klipper installed version
    expect(text).toContain('v0.13.0-699') // klipper latest (update target)
    expect(text).toContain('v0.0.26') // not-installed component's latest available version
  })
})
