import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

// Mock the hardware-browser API so we can assert how the catalog fetches.
const { fetchDrivers, fetchDriverDetail, fetchRelated } = vi.hoisted(() => ({
  fetchDrivers: vi.fn(),
  fetchDriverDetail: vi.fn(),
  fetchRelated: vi.fn(),
}))
vi.mock('../api', () => ({ fetchDrivers, fetchDriverDetail, fetchRelated }))

import DriversPanel from '../DriversPanel.vue'
import { useEntityFocus } from '../useEntityFocus'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('DriversPanel deep-link clears the Klipper-only facet (DB-3b regression lock)', () => {
  beforeEach(() => {
    fetchDrivers.mockReset()
    fetchDriverDetail.mockReset()
    fetchRelated.mockReset()
    fetchDrivers.mockResolvedValue({
      drivers: [{ driver_id: 'a4988', name: 'A4988', klipperSupported: false }],
      total: 1,
    })
    fetchDriverDetail.mockResolvedValue({ driver_id: 'a4988', name: 'A4988', specs: {} })
    fetchRelated.mockResolvedValue({ type: 'driver', id: 'a4988', groups: {}, counts: {} })
    useEntityFocus().clear()
  })

  it('a cross-link focus resets klipperOnly so a standalone driver still surfaces', async () => {
    const w = mount(DriversPanel, plugins())
    await flushPromises()

    // user enables the Klipper-only facet
    await w.find('input[type=checkbox]').setValue(true)
    await flushPromises()
    fetchDrivers.mockClear()

    // a RelatedChips cross-link targets a standalone (non-Klipper) driver
    useEntityFocus().focusEntity({ tab: 'drivers', id: 'a4988', name: 'A4988' })
    await flushPromises()

    // the deep-link search must have run with the facet cleared, or the target would be filtered out
    const calls = fetchDrivers.mock.calls
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1][0]).toMatchObject({ klipperOnly: false })
  })
})
