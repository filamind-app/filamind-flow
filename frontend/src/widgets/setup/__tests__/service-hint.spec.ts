import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

// A first-party app that carries a managed-service install subcommand (3d → agent). The widget
// should surface a copyable printer-side one-liner built from the repo + subcommand.
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

describe('Setup widget: managed-service install hint', () => {
  it('surfaces the agent one-liner + copy button for a first-party app with service_install', async () => {
    const w = mount(SetupWidget, { global: { plugins: [i18n, createPinia()] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('Adds the FilaMind 3d agent (managed service).') // the hint
    expect(text).toContain('raw.githubusercontent.com/filamind-app/filamind-3d') // built from repo
    expect(text).toContain('bash -s -- agent') // the subcommand
    const copy = i18n.global.t('setup.suite.copy') as string
    expect(w.findAll('button').some((b) => b.text() === copy)).toBe(true)
  })
})
