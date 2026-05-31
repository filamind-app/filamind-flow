import { describe, expect, it } from 'vitest'

import { compareFirmware } from '../compare'
import type { ExternalFirmware } from '../types'

function fw(over: Partial<ExternalFirmware>): ExternalFirmware {
  return {
    name: 'x',
    label: 'x',
    method: 'serial',
    offset: '',
    interface: 'can0',
    notes: '',
    filename: 'x.bin',
    size: 100,
    detected_version: null,
    detected_mcu: null,
    detected_app: null,
    detected_config: null,
    ...over,
  }
}

describe('compareFirmware', () => {
  it('classifies metadata + config into same / changed / a_only / b_only', () => {
    const a = fw({
      name: 'a',
      size: 100,
      detected_app: 'Klipper',
      detected_version: 'v1',
      detected_mcu: 'stm32f103xe',
      detected_config: { MCU: 'stm32f103xe', CLOCK_FREQ: '72000000', ONLY_A: '1' },
    })
    const b = fw({
      name: 'b',
      size: 200,
      detected_app: 'Klipper',
      detected_version: 'v2',
      detected_mcu: 'stm32f103xe',
      detected_config: { MCU: 'stm32f103xe', CLOCK_FREQ: '100000000', ONLY_B: '9' },
    })

    const r = compareFirmware(a, b)

    const meta = Object.fromEntries(r.meta.map((m) => [m.key, m.status]))
    expect(meta.app).toBe('same')
    expect(meta.version).toBe('changed')
    expect(meta.mcu).toBe('same')
    expect(meta.size).toBe('changed')

    const cfg = Object.fromEntries(r.config.map((c) => [c.key, c.status]))
    expect(cfg.MCU).toBe('same')
    expect(cfg.CLOCK_FREQ).toBe('changed')
    expect(cfg.ONLY_A).toBe('a_only')
    expect(cfg.ONLY_B).toBe('b_only')

    // config rows are sorted by key; counts tally only the config diff.
    expect(r.config.map((c) => c.key)).toEqual(['CLOCK_FREQ', 'MCU', 'ONLY_A', 'ONLY_B'])
    expect(r.counts).toEqual({ same: 1, changed: 1, a_only: 1, b_only: 1 })
  })

  it('treats two files with no baked-in config as an empty config diff', () => {
    const r = compareFirmware(fw({ detected_config: null }), fw({ detected_config: null }))
    expect(r.config).toEqual([])
    expect(r.counts).toEqual({ same: 0, changed: 0, a_only: 0, b_only: 0 })
  })
})
