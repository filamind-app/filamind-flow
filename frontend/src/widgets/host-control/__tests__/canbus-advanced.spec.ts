import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

const { setCanParams, restartCanBus } = vi.hoisted(() => ({
  setCanParams: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
  restartCanBus: vi.fn(() =>
    Promise.resolve({ interface: 'can0', ok: true, refused: false, output: '' }),
  ),
}))

vi.mock('../api', () => ({
  // A DOWN, BUS-OFF interface: advanced editor is enabled and the restart button shows.
  fetchCanBuses: () =>
    Promise.resolve([
      {
        interface: 'can0',
        driver: 'gs_usb',
        bitrate: 1000000,
        link_up: false,
        state: 'BUS-OFF',
        errors_rx: 250,
        errors_tx: 250,
        txqueuelen: 128,
        params: { sjw: 1, sample_point: 0.875, restart_ms: 0, flags: { listen_only: false } },
        limits: { sjw_max: 4, fd_supported: false },
      },
    ]),
  setCanLink: vi.fn(),
  setCanBitrate: vi.fn(),
  setCanParams,
  restartCanBus,
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

const t = (k: string) => i18n.global.t(k)
const byText = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').find((b) => b.text().includes(text))

describe('Host Control: CAN advanced parameters', () => {
  it('applies advanced parameters (timing + control-mode flags) when down', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    await byText(w, t('hostControl.canbus.advanced'))!.trigger('click')
    await flushPromises()
    // the advanced editor renders the parameter labels + flags
    expect(w.text()).toContain(t('hostControl.canbus.samplePoint'))
    expect(w.text()).toContain(t('hostControl.canbus.flag.triple_sampling'))
    // Apply asks to confirm first (it cycles the bus + restarts Klipper), then fires.
    await byText(w, t('hostControl.canbus.applyParams'))!.trigger('click')
    expect(setCanParams).not.toHaveBeenCalled()
    await byText(w, t('hostControl.canbus.confirm'))!.trigger('click')
    await flushPromises()
    expect(setCanParams).toHaveBeenCalledTimes(1)
    const [iface, params, restart] = setCanParams.mock.calls[0] as unknown as [
      string,
      Record<string, unknown>,
      boolean,
    ]
    expect(iface).toBe('can0')
    // every control-mode flag is sent as a boolean; seeded sjw/sample-point carried through
    expect(params.listen_only).toBe(false)
    expect(params.triple_sampling).toBe(false)
    expect(params.sjw).toBe(1)
    // restart=true so the backend FIRMWARE_RESTARTs Klipper after re-upping the bus
    expect(restart).toBe(true)
  })

  it('shows a Restart bus button for a BUS-OFF controller and calls the API', async () => {
    const w = mount(CanBusPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const restart = byText(w, t('hostControl.canbus.restart'))
    expect(restart).toBeTruthy()
    await restart!.trigger('click')
    await flushPromises()
    expect(restartCanBus).toHaveBeenCalledWith('can0')
  })
})
