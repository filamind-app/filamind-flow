import { describe, expect, it } from 'vitest'

import {
  axisHeading,
  capabilityChips,
  chopperLabel,
  currentLabel,
  driverHealth,
  driverModelLabel,
  temperatureLabel,
} from '../format'
import type { TmcDriver } from '../types'

function driver(overrides: Partial<TmcDriver> = {}): TmcDriver {
  return {
    stepper: 'stepper_x',
    model: 'tmc2209',
    axis: 'X',
    run_current: 1.08,
    hold_current: 0.79,
    run_current_config: 1.1,
    hold_current_config: 0.8,
    sense_resistor: 0.11,
    microsteps: 16,
    interpolate: true,
    stealthchop_threshold: 0,
    chopper_mode: 'SpreadCycle',
    stallguard_field: 'sgthrs',
    stallguard_threshold: 70,
    temperature: null,
    drv_status: null,
    capabilities: { stealthchop: true, spreadcycle: true, stallguard: true },
    registers: {},
    ...overrides,
  }
}

describe('driverModelLabel', () => {
  it('uppercases the model', () => {
    expect(driverModelLabel('tmc2209')).toBe('TMC2209')
  })
})

describe('currentLabel', () => {
  it('shows the configured value when it differs from live', () => {
    expect(currentLabel(1.08, 1.1)).toBe('1.08 A (set 1.10)')
  })
  it('omits the configured value when it matches', () => {
    expect(currentLabel(1.1, 1.1)).toBe('1.10 A')
  })
  it('falls back to the configured value when live is missing', () => {
    expect(currentLabel(null, 0.8)).toBe('0.80 A')
  })
  it('renders an em dash when nothing is known', () => {
    expect(currentLabel(null, null)).toBe('—')
  })
})

describe('chopperLabel', () => {
  it('labels SpreadCycle', () => {
    expect(chopperLabel(driver({ chopper_mode: 'SpreadCycle' }))).toBe('SpreadCycle')
  })
  it('includes the StealthChop threshold velocity', () => {
    expect(chopperLabel(driver({ chopper_mode: 'StealthChop', stealthchop_threshold: 5 }))).toBe(
      'StealthChop < 5 mm/s',
    )
  })
  it('drops a sentinel-high threshold', () => {
    expect(
      chopperLabel(driver({ chopper_mode: 'StealthChop', stealthchop_threshold: 999999 })),
    ).toBe('StealthChop')
  })
})

describe('driverHealth', () => {
  it('is idle when the motor reports no drv_status', () => {
    expect(driverHealth(driver({ drv_status: null })).tone).toBe('idle')
  })
  it('is ok when enabled with no faults', () => {
    expect(driverHealth(driver({ drv_status: { otpw: 0, ot: 0 } })).tone).toBe('ok')
  })
  it('warns on an over-temperature pre-warning', () => {
    expect(driverHealth(driver({ drv_status: { otpw: 1 } })).tone).toBe('warn')
  })
  it('faults on a short to ground', () => {
    expect(driverHealth(driver({ drv_status: { s2ga: 1 } })).tone).toBe('error')
  })
})

describe('temperatureLabel', () => {
  it('formats a live reading', () => {
    expect(temperatureLabel(driver({ temperature: 42.5 }))).toBe('42.5 °C')
  })
  it('explains the missing sensor on a 2209', () => {
    expect(temperatureLabel(driver({ model: 'tmc2209', temperature: null }))).toBe('no sensor')
  })
})

describe('capabilityChips', () => {
  it('returns present capabilities in a stable order, uppercased', () => {
    expect(
      capabilityChips({ stallguard: true, stealthchop: true, coolstep: false, spreadcycle: true }),
    ).toEqual(['STEALTHCHOP', 'SPREADCYCLE', 'STALLGUARD'])
  })
})

describe('axisHeading', () => {
  it('labels a motion axis', () => {
    expect(axisHeading(driver({ axis: 'X' }))).toBe('X axis')
  })
  it('labels the extruder', () => {
    expect(axisHeading(driver({ stepper: 'extruder', axis: 'E' }))).toBe('Extruder')
  })
  it('labels a second extruder', () => {
    expect(axisHeading(driver({ stepper: 'extruder1', axis: 'E1' }))).toBe('Extruder 1')
  })
})
