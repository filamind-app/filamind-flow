import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

/** The CAN-termination advisory renders findings via boardTopology.termination.finding.<code>
 *  (middle_off carries a {count}) and type/default labels. Verify the keys resolve + interpolate. */
describe('Board Topology: CAN termination i18n', () => {
  const t = i18n.global.t
  const te = i18n.global.te

  it('interpolates the >2-node correction finding', () => {
    const msg = t('boardTopology.termination.finding.middle_off', { count: 3 })
    expect(msg).toContain('3')
    expect(msg).not.toContain('{count}')
  })

  it('interpolates the live bus-error finding (interface + state)', () => {
    const msg = t('boardTopology.termination.finding.bus_error', {
      interface: 'can0',
      state: 'BUS-OFF',
    })
    expect(msg).toContain('can0')
    expect(msg).toContain('BUS-OFF')
    expect(msg).not.toContain('{interface}')
    expect(msg).not.toContain('{state}')
  })

  it('interpolates the healthy reading-based verdict (bus_ok)', () => {
    const msg = t('boardTopology.termination.finding.bus_ok', {
      interface: 'can0',
      state: 'ERROR-ACTIVE',
    })
    expect(msg).toContain('can0')
    expect(msg).toContain('ERROR-ACTIVE')
    expect(msg).not.toContain('{interface}')
    expect(msg).not.toContain('{state}')
  })

  it('has every finding code, type label and default label', () => {
    for (const c of ['rule', 'both_ends', 'middle_off', 'single_node', 'bus_error', 'bus_ok'])
      expect(te('boardTopology.termination.finding.' + c)).toBe(true)
    for (const tp of ['jumper', 'solder_bridge', 'switch', 'fixed', 'none'])
      expect(te('boardTopology.termination.type.' + tp)).toBe(true)
    for (const d of ['on', 'off', 'unknown'])
      expect(te('boardTopology.termination.default.' + d)).toBe(true)
    expect(te('boardTopology.termination.title')).toBe(true)
    expect(te('boardTopology.termination.role.adapter')).toBe(true)
  })
})
