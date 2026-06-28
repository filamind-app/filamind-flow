import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import ManualAdditionModal from '../ManualAdditionModal.vue'
import type { ManualAddition } from '../types'

const stubs = { HardwarePicker: { template: '<div class="hw-picker-stub" />' } }

function mountModal(entry: ManualAddition | null = null) {
  return mount(ManualAdditionModal, {
    props: { open: true, entry, busy: false },
    global: { plugins: [i18n], stubs },
  })
}

describe('Board Topology: manual addition modal', () => {
  it('requires a name for an MCU and emits the entry on save', async () => {
    const w = mountModal(null)
    await flushPromises()
    const save = w
      .findAll('button')
      .find((b) => b.text() === i18n.global.t('boardTopology.manual.save'))
    expect(save!.attributes('disabled')).toBeDefined() // blank name -> disabled
    await w.find('input[type="text"]').setValue('toolhead')
    expect(save!.attributes('disabled')).toBeUndefined()
    await save!.trigger('click')
    const emitted = w.emitted('submit')
    expect(emitted).toBeTruthy()
    const entry = emitted![0][0] as ManualAddition
    expect(entry).toMatchObject({ kind: 'mcu', name: 'toolhead', connection: 'unknown' })
  })

  it('pre-fills the form when editing and locks the kind', async () => {
    const w = mountModal({ id: 'manual-1', kind: 'canbus', interface: 'can0', board_id: 'u2c-all' })
    await flushPromises()
    // kind select is disabled in edit mode
    expect(w.find('select').attributes('disabled')).toBeDefined()
    const save = w
      .findAll('button')
      .find((b) => b.text() === i18n.global.t('boardTopology.manual.save'))
    await save!.trigger('click')
    const entry = w.emitted('submit')![0][0] as ManualAddition
    expect(entry).toMatchObject({ id: 'manual-1', kind: 'canbus', interface: 'can0' })
  })
})
