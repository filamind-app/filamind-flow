import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

const { setCanLink, setCanBitrate } = vi.hoisted(() => ({
  setCanLink: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
  setCanBitrate: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
}))

vi.mock('../api', () => ({
  fetchCanBuses: () =>
    Promise.resolve([
      {
        interface: 'can0',
        driver: 'gs_usb',
        bitrate: 1000000,
        link_up: true,
        state: 'ERROR-ACTIVE',
        errors_rx: 0,
        errors_tx: 0,
        txqueuelen: 128,
        board_id: 'u2c',
        board_match: 'suggested',
      },
    ]),
  setCanLink,
  setCanBitrate,
  setCanParams: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
  restartCanBus: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
  HostActionError: class HostActionError extends Error {
    constructor(
      message: string,
      readonly status: number,
    ) {
      super(message)
    }
  },
}))

import CanBusPanel from '../CanBusPanel.vue'

describe('Host Control: CAN bus panel', () => {
  it('renders the interface status and a down-disabled bitrate control when up', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('can0')
    expect(text).toContain('gs_usb')
    expect(text).toContain('ERROR-ACTIVE')
    expect(text).toContain('1000 kbit/s')
    // up -> the bitrate select is disabled (SocketCAN can't retime a running controller)
    expect(w.find('select').attributes('disabled')).toBeDefined()
  })

  it('asks to confirm before bringing the bus down', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const down = w
      .findAll('button')
      .find((b) => b.text() === i18n.global.t('hostControl.canbus.bringDown'))
    expect(down).toBeTruthy()
    await down!.trigger('click')
    // confirm step shown, action not yet sent
    expect(setCanLink).not.toHaveBeenCalled()
    const confirm = w
      .findAll('button')
      .find((b) => b.text() === i18n.global.t('hostControl.canbus.confirm'))
    await confirm!.trigger('click')
    await flushPromises()
    expect(setCanLink).toHaveBeenCalledWith('can0', false)
  })
})
