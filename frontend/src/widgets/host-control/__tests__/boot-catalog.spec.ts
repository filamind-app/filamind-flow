import { describe, expect, it } from 'vitest'

import { BOOT_CATALOG, type BootItem, opsForValue, readValue } from '../bootCatalog'
import type { BootFile } from '../types'

/** Find a catalog item by key on a platform (for its real kind/argKey/token). */
function item(platform: 'armbian' | 'rpi', key: string): BootItem {
  const found = BOOT_CATALOG[platform].flatMap((g) => g.items).find((i) => i.key === key)
  if (!found) throw new Error(`no catalog item ${key}`)
  return found
}

function configFile(part: Partial<BootFile>): BootFile {
  return {
    name: 'config.txt',
    path: '/boot/config.txt',
    exists: true,
    format: 'config.txt',
    raw_lines: 1,
    backups: [],
    dtparams: [],
    kv: [],
    overlays: [],
    ...part,
  }
}

describe('bootCatalog readValue (value + scope aware)', () => {
  it('kv_toggle reads the VALUE, not mere presence', () => {
    const it0 = item('rpi', 'enable_uart')
    expect(
      readValue(configFile({ kv: [{ key: 'enable_uart', value: '0', section: null }] }), it0),
    ).toBe('off')
    expect(
      readValue(configFile({ kv: [{ key: 'enable_uart', value: '1', section: null }] }), it0),
    ).toBe('on')
    expect(readValue(configFile({ kv: [] }), it0)).toBe('off')
  })

  it('dtparam_toggle treats =off as off and a bare dtparam as on', () => {
    const spi = item('rpi', 'spi')
    expect(
      readValue(configFile({ dtparams: [{ key: 'spi', value: 'off', section: null }] }), spi),
    ).toBe('off')
    expect(
      readValue(configFile({ dtparams: [{ key: 'spi', value: 'on', section: null }] }), spi),
    ).toBe('on')
    expect(
      readValue(configFile({ dtparams: [{ key: 'spi', value: null, section: null }] }), spi),
    ).toBe('on')
  })

  it('ignores a model-specific [pi4] scope and uses the last [all]/global value', () => {
    const gpu = item('rpi', 'gpu_mem')
    // only under [pi4] -> not the editable value the card reflects
    expect(
      readValue(configFile({ kv: [{ key: 'gpu_mem', value: '256', section: 'pi4' }] }), gpu),
    ).toBe('')
    // global then [all] -> the [all] value wins (last editable)
    const f = configFile({
      kv: [
        { key: 'gpu_mem', value: '64', section: null },
        { key: 'gpu_mem', value: '128', section: 'all' },
      ],
    })
    expect(readValue(f, gpu)).toBe('128')
  })

  it('dtoverlay_select returns the matching variant, or "" for an out-of-catalog value (never a phantom)', () => {
    const can = item('rpi', 'can_mcp2515')
    const known = configFile({
      overlays: [
        { name: 'mcp2515-can0', params: 'oscillator=16000000,interrupt=25', section: null },
      ],
    })
    expect(readValue(known, can)).toBe('16000000')
    const unknown = configFile({
      overlays: [
        { name: 'mcp2515-can0', params: 'oscillator=24000000,interrupt=25', section: null },
      ],
    })
    expect(readValue(unknown, can)).toBe('') // NOT '8000000'
  })
})

describe('bootCatalog opsForValue', () => {
  it('kv_toggle off->on emits set_kv with onValue (so an =0 host can be enabled)', () => {
    expect(opsForValue(item('rpi', 'enable_uart'), 'off', 'on')).toEqual([
      { op: 'set_kv', key: 'enable_uart', value: '1' },
    ])
  })

  it('dtoverlay_select ""->variant removes then adds with the templated params', () => {
    const ops = opsForValue(item('rpi', 'can_mcp2515'), '', '16000000')
    expect(ops).toEqual([
      { op: 'set_dtparam', key: 'spi', value: 'on' },
      { op: 'remove_dtoverlay', name: 'mcp2515-can0' },
      { op: 'add_dtoverlay', name: 'mcp2515-can0', params: 'oscillator=16000000,interrupt=25' },
    ])
  })

  it('overlay_select swap removes the old variant and adds the new', () => {
    expect(opsForValue(item('armbian', 'spi_accel'), 'spidev1_0', 'spidev1_1')).toEqual([
      { op: 'remove_overlay', name: 'spidev1_0' },
      { op: 'add_overlay', name: 'spidev1_1' },
    ])
  })
})
