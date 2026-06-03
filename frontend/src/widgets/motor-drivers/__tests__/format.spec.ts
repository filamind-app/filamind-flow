import { describe, expect, it } from 'vitest'

import {
  axisHeading,
  capabilityChips,
  chopperLabel,
  currentLabel,
  driverHealth,
  driverModelLabel,
  effectiveCapabilities,
  filterMotors,
  interfaceLabel,
  maxCurrentLabel,
  motorSpecLabel,
  nearCurrentCap,
  temperatureLabel,
} from '../format'
import type { DriverInfo, MotorSpec, TmcDriver } from '../types'

function motor(overrides: Partial<MotorSpec> = {}): MotorSpec {
  return {
    manufacturer: 'LDO Motors',
    model: 'ldo-42sth48-2004ah',
    resistance_ohm: 1.5,
    inductance_H: 0.0028,
    holding_torque_Nm: 0.45,
    max_current_A: 2.0,
    steps_per_rev: 200,
    source: 'motor_database.cfg',
    ...overrides,
  }
}

function info(overrides: Partial<DriverInfo> = {}): DriverInfo {
  return {
    model: 'tmc2209',
    name: 'TMC2209',
    interface: 'UART',
    max_current_a: 2.0,
    current_note: null,
    microsteps: 256,
    stealthchop: true,
    spreadcycle: true,
    coolstep: true,
    stallguard: true,
    stallguard_field: 'sgthrs',
    sensorless: true,
    temperature: false,
    aliases: [],
    notes: null,
    ...overrides,
  }
}

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
    info: null,
    motor: null,
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

describe('catalog-aware helpers', () => {
  it('prefers authoritative catalog capabilities when info is present', () => {
    const d = driver({
      capabilities: { stallguard: true }, // config-inferred (incomplete)
      info: info({ stealthchop: true, spreadcycle: true, coolstep: true, stallguard: false }),
    })
    const caps = effectiveCapabilities(d)
    expect(caps.coolstep).toBe(true) // from the catalog, not the inferred set
    expect(caps.stallguard).toBe(false) // catalog overrides the inferred true
  })
  it('falls back to inferred capabilities when info is absent', () => {
    const d = driver({ info: null, capabilities: { stealthchop: true } })
    expect(effectiveCapabilities(d)).toEqual({ stealthchop: true })
  })
  it('formats interface and current cap from the catalog', () => {
    const d = driver({ info: info({ interface: 'UART/SPI', max_current_a: 3 }) })
    expect(interfaceLabel(d)).toBe('UART·SPI')
    expect(maxCurrentLabel(d)).toBe('≤ 3.0 A')
  })
  it('returns empty strings when there is no catalog info', () => {
    const d = driver({ info: null })
    expect(interfaceLabel(d)).toBe('')
    expect(maxCurrentLabel(d)).toBe('')
  })
  it('flags a run current near the rated cap', () => {
    expect(nearCurrentCap(driver({ run_current: 1.9, info: info({ max_current_a: 2 }) }))).toBe(
      true,
    )
    expect(nearCurrentCap(driver({ run_current: 1.0, info: info({ max_current_a: 2 }) }))).toBe(
      false,
    )
    expect(nearCurrentCap(driver({ info: null }))).toBe(false)
  })
})

describe('motorSpecLabel', () => {
  it('formats the key datasheet specs', () => {
    expect(motorSpecLabel(motor())).toBe('0.45 Nm · 2.0 A · 1.5 Ω · 2.8 mH')
  })
  it('omits missing fields and falls back to an em dash', () => {
    expect(
      motorSpecLabel(motor({ resistance_ohm: null, inductance_H: null, max_current_A: null })),
    ).toBe('0.45 Nm')
    expect(
      motorSpecLabel(
        motor({
          holding_torque_Nm: null,
          resistance_ohm: null,
          inductance_H: null,
          max_current_A: null,
        }),
      ),
    ).toBe('—')
  })
})

describe('filterMotors', () => {
  const catalog = [
    motor({ manufacturer: 'LDO Motors', model: 'ldo-42sth48-2004ah' }),
    motor({ manufacturer: 'Moons', model: 'ms17hd2p4100' }),
    motor({ manufacturer: 'OMC / StepperOnline', model: '17hs19-2004s1' }),
  ]
  it('returns all motors for an empty query', () => {
    expect(filterMotors(catalog, '  ')).toHaveLength(3)
  })
  it('matches on model substring', () => {
    expect(filterMotors(catalog, '42sth').map((m) => m.model)).toEqual(['ldo-42sth48-2004ah'])
  })
  it('matches on manufacturer, case-insensitively', () => {
    expect(filterMotors(catalog, 'moons').map((m) => m.model)).toEqual(['ms17hd2p4100'])
  })
})
