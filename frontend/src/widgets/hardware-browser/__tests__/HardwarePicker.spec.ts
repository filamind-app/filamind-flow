import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

const { fetchBoards, fetchDrivers, fetchMotors, fetchHosts } = vi.hoisted(() => ({
  fetchBoards: vi.fn(),
  fetchDrivers: vi.fn(),
  fetchMotors: vi.fn(),
  fetchHosts: vi.fn(),
}))
vi.mock('../api', () => ({ fetchBoards, fetchDrivers, fetchMotors, fetchHosts }))

import HardwarePicker from '../HardwarePicker.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

describe('HardwarePicker (DB-3d)', () => {
  beforeEach(() => {
    fetchMotors.mockReset()
    // two pages to exercise the paging-the-whole-catalog loop
    fetchMotors.mockImplementation(({ offset }: { offset: number }) =>
      Promise.resolve(
        offset === 0
          ? {
              motors: [
                { motor_id: 'ldo-42sth48', name: 'LDO 42STH48', manufacturer: 'LDO', nema: '17' },
              ],
              total: 2,
            }
          : {
              motors: [
                { motor_id: 'moons-17', name: 'MOONS 17', manufacturer: 'MOONS', nema: '17' },
              ],
              total: 2,
            },
      ),
    )
  })

  it('loads the full catalog and emits the picked entity for auto-fill', async () => {
    const w = mount(HardwarePicker, { ...plugins(), props: { type: 'motors', modelValue: null } })
    await flushPromises()
    // both pages fetched
    expect(fetchMotors).toHaveBeenCalledTimes(2)
    // simulate ComboSelect choosing an id
    const combo = w.findComponent({ name: 'ComboSelect' })
    combo.vm.$emit('update:modelValue', 'moons-17')
    await flushPromises()
    const picked = w.emitted('update:modelValue')
    const sel = w.emitted('select')
    expect(picked?.[0]).toEqual(['moons-17'])
    expect((sel?.[0]?.[0] as { motor_id: string }).motor_id).toBe('moons-17')
  })
})
