import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import GuidedWizard from '../GuidedWizard.vue'
import HomingPanel from '../HomingPanel.vue'
import LiveMonitor from '../LiveMonitor.vue'
import MotorDriversWidget from '../MotorDriversWidget.vue'
import MotorPicker from '../MotorPicker.vue'
import MotorSyncPanel from '../MotorSyncPanel.vue'
import RecommendPanel from '../RecommendPanel.vue'
import RegisterEditor from '../RegisterEditor.vue'
import SensorlessPanel from '../SensorlessPanel.vue'
import type { TmcDriver } from '../types'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

function noLeak(text: string): void {
  const leaked = text.match(/motorDrivers\.[a-zA-Z]/)
  expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
}

const drv: TmcDriver = {
  stepper: 'stepper_x',
  model: 'tmc2209',
  axis: 'X',
  run_current: 0.8,
  hold_current: 0.5,
  run_current_config: 0.8,
  hold_current_config: 0.5,
  sense_resistor: 0.11,
  rref: null,
  microsteps: 16,
  interpolate: true,
  stealthchop_threshold: null,
  chopper_mode: 'SpreadCycle',
  stallguard_field: 'sgthrs',
  stallguard_threshold: 100,
  temperature: null,
  drv_status: null,
  capabilities: {},
  registers: {},
  info: null,
  motor: null,
  current_cap: 2.0,
  homing_method: 'sensorless',
  endstop_pin: 'tmc2209_stepper_x:virtual_endstop',
  homing_note: null,
}

/** Mount, expand the first collapsible toggle if present, and assert no raw key path leaks. */
async function mountExpand(component: unknown, props: Record<string, unknown> = {}): Promise<void> {
  const w = mount(component as never, { props: props as never, ...plugins() })
  const btn = w.find('button')
  if (btn.exists()) await btn.trigger('click')
  noLeak(w.text())
}

describe('Motor Drivers templates render through i18n (no leaked keys)', () => {
  it('MotorDriversWidget — chrome, intro <i18n-t>, steps via tm()', () => {
    const w = mount(MotorDriversWidget, plugins())
    const text = w.text()
    noLeak(text)
    expect(text).toContain('Every TMC stepper driver') // intro (always rendered)
  })

  it('MotorSyncPanel — about <i18n-t>', () => mountExpand(MotorSyncPanel))
  it('LiveMonitor', () => mountExpand(LiveMonitor, { driver: drv }))
  it('RecommendPanel', () => mountExpand(RecommendPanel, { driver: drv, defaultOpen: true }))
  it('HomingPanel — sensorless path', () => mountExpand(HomingPanel, { driver: drv }))
  it('SensorlessPanel — intro/testHome <i18n-t>', () =>
    mountExpand(SensorlessPanel, { driver: drv }))
  it('RegisterEditor — liveOnly <i18n-t>', () => mountExpand(RegisterEditor, { driver: drv }))
  it('MotorPicker', () =>
    mountExpand(MotorPicker, { stepper: 'stepper_x', assigned: null, catalog: [] }))
  it('GuidedWizard — tuningHeader/step <i18n-t>', () =>
    mountExpand(GuidedWizard, { drivers: [drv], catalog: [] }))
})
