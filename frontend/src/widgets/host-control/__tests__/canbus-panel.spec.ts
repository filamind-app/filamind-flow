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
  restartKlipper: vi.fn(() => Promise.resolve({ ok: true, refused: false, output: '' })),
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
  it('renders the interface status and keeps controls editable when up', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('can0')
    expect(text).toContain('gs_usb')
    expect(text).toContain('ERROR-ACTIVE')
    expect(text).toContain('1000 kbit/s')
    // up -> the bitrate select is now editable; Apply cycles the bus down/up + restarts Klipper
    expect(w.find('select').attributes('disabled')).toBeUndefined()
  })

  it('confirms, sets the bitrate with restart=true, and restarts Klipper from its own button', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const t = i18n.global.t
    const byText = (s: string) => w.findAll('button').find((b) => b.text() === s)
    // Set bitrate asks to confirm first (it drops the bus + restarts Klipper)
    await byText(t('hostControl.canbus.setBitrate'))!.trigger('click')
    expect(setCanBitrate).not.toHaveBeenCalled()
    await byText(t('hostControl.canbus.confirm'))!.trigger('click')
    await flushPromises()
    expect(setCanBitrate).toHaveBeenCalledWith('can0', 1000000, true)
    // the standalone "Restart Klipper & MCUs" button (confirm then fire)
    await byText(t('hostControl.canbus.restartKlipper'))!.trigger('click')
    await byText(t('hostControl.canbus.confirm'))!.trigger('click')
    await flushPromises()
    const { restartKlipper } = (await import('../api')) as unknown as {
      restartKlipper: ReturnType<typeof vi.fn>
    }
    expect(restartKlipper).toHaveBeenCalled()
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
