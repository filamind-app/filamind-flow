import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

// A first-party app with an ADDITIONAL managed deployment (3d → agent). The widget should offer a
// real "Install agent" button (carrying the hint as its title), NOT a copyable one-liner.
vi.mock('../api', () => ({
  fetchCatalog: () =>
    Promise.resolve({
      schema: 1,
      groups: [
        {
          group: 'apps',
          components: [
            {
              id: 'filamind-3d',
              name: 'FilaMind 3d',
              kind: 'web-ui',
              repo: 'filamind-app/filamind-3d',
              type: 'web',
              first_party: true,
              default_port: 8089,
              service_install: 'agent',
              service_install_hint: 'Adds the FilaMind 3d agent (managed service).',
            },
          ],
        },
      ],
    }),
  fetchStatus: () =>
    Promise.resolve({
      status: {
        'filamind-3d': {
          status: 'installed',
          version: 'ea845fe',
          latest: 'ea845fe',
          updateAvailable: false,
        },
      },
      writesEnabled: true,
      autoUpdate: { enabled: false, intervalHours: 24 },
    }),
  installComponent: vi.fn(),
  installComponentStream: vi.fn(),
  updateComponent: vi.fn(),
  removeComponent: vi.fn(),
  restartComponent: vi.fn(),
  setPort: vi.fn(),
  setWrites: vi.fn(),
  setAutoUpdate: vi.fn(),
}))

import SetupWidget from '../SetupWidget.vue'

describe('Setup widget: managed-service install button', () => {
  it('offers an "Install agent" button (not a copy one-liner) for a first-party service_install', async () => {
    const w = mount(SetupWidget, { global: { plugins: [i18n, createPinia()] } })
    await flushPromises()

    const label = i18n.global.t('setup.installNamed', { x: 'agent' }) as string // "Install agent"
    const btn = w.findAll('button').find((b) => b.text() === label)
    expect(btn).toBeTruthy()
    // The hint rides along as the button's title (replaces the old explanatory paragraph).
    expect(btn!.attributes('title')).toContain('Adds the FilaMind 3d agent')
    // The old copyable one-liner is gone — it's a real GUI-run install now.
    expect(w.text()).not.toContain('bash -s -- agent')
  })
})
