import { describe, it, expect, vi, afterEach } from 'vitest'

import {
  hostMode,
  isSuiteHost,
  isMainsailHost,
  showMainsailLink,
  isWidgetEnabled,
  detectBackUi,
} from '@/core/host/adapter'

const loc = { protocol: 'http:', hostname: 'printer.local' }
const okFetch = (name: string) =>
  (() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ name }) })) as unknown as typeof fetch

describe('host adapter (dual-host)', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('defaults to the Mainsail host when VITE_HOST_MODE is unset', () => {
    expect(hostMode()).toBe('mainsail')
    expect(isMainsailHost()).toBe(true)
    expect(isSuiteHost()).toBe(false)
  })

  it('shows the "back to Mainsail" link only on the Mainsail host', () => {
    expect(showMainsailLink()).toBe(true)
  })

  it('hides suite-only widgets on the default (Mainsail) host but keeps shared ones', () => {
    expect(isWidgetEnabled('machine-doctor')).toBe(true)
    expect(isWidgetEnabled('host-control')).toBe(true)
    expect(isWidgetEnabled('setup')).toBe(true) // ships in both hosts
    expect(isWidgetEnabled('remote-control')).toBe(false) // suite-exclusive
  })

  it('enables the suite-only remote-control widget when VITE_HOST_MODE=suite', () => {
    vi.stubEnv('VITE_HOST_MODE', 'suite')
    expect(isSuiteHost()).toBe(true)
    expect(isWidgetEnabled('remote-control')).toBe(true)
    expect(isWidgetEnabled('machine-doctor')).toBe(true) // shared widgets still enabled
  })

  it('detectBackUi recognises Mainsail and Fluidd from the host manifest', async () => {
    expect(await detectBackUi({ location: loc, fetchImpl: okFetch('Mainsail') })).toEqual({
      name: 'Mainsail',
      url: 'http://printer.local/',
    })
    expect((await detectBackUi({ location: loc, fetchImpl: okFetch('Fluidd') })).name).toBe(
      'Fluidd',
    )
  })

  it('detectBackUi falls back to a generic (empty) name on any probe failure', async () => {
    const boom = (() => Promise.reject(new Error('CORS'))) as unknown as typeof fetch
    expect((await detectBackUi({ location: loc, fetchImpl: boom })).name).toBe('')
    const unknown = okFetch('SomethingElse')
    expect((await detectBackUi({ location: loc, fetchImpl: unknown })).name).toBe('')
  })
})
