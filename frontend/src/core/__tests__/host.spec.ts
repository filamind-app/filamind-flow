import { describe, it, expect, vi, afterEach } from 'vitest'

import {
  hostMode,
  isSuiteHost,
  isMainsailHost,
  showMainsailLink,
  isWidgetEnabled,
} from '@/core/host/adapter'

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
})
