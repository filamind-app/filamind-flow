import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

const { fetchBoards, fetchBoardDetail, fetchRelated, fetchFacets } = vi.hoisted(() => ({
  fetchBoards: vi.fn(),
  fetchBoardDetail: vi.fn(),
  fetchRelated: vi.fn(),
  fetchFacets: vi.fn(),
}))
vi.mock('../api', () => ({ fetchBoards, fetchBoardDetail, fetchRelated, fetchFacets }))

import BoardsPanel from '../BoardsPanel.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('BoardsPanel facets (DB-3c)', () => {
  beforeEach(() => {
    fetchBoards.mockReset()
    fetchFacets.mockReset()
    fetchBoards.mockResolvedValue({ boards: [], total: 0 })
    fetchFacets.mockResolvedValue({
      boardClass: ['mainboard', 'toolhead'],
      nema: ['17'],
      kind: ['sbc'],
    })
  })

  it('loads facet options and applies a manufacturer filter to the fetch', async () => {
    const w = mount(BoardsPanel, plugins())
    await flushPromises()
    expect(fetchFacets).toHaveBeenCalled()

    const manInput = w.findAll('input').find((i) => i.attributes('placeholder') === 'Manufacturer')
    expect(manInput).toBeTruthy()
    await manInput!.setValue('BTT')
    await manInput!.trigger('keyup.enter')
    await flushPromises()

    const last = fetchBoards.mock.calls.at(-1)?.[0]
    expect(last).toMatchObject({ manufacturer: 'BTT' })
  })
})
