import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import CsvSourceChooser from '../CsvSourceChooser.vue'
import InputShapingWidget from '../InputShapingWidget.vue'
import ResonanceCompare from '../ResonanceCompare.vue'
import ResonanceFromPrinter from '../ResonanceFromPrinter.vue'
import type { VibrationsProfile } from '../types'
import VibrationsProfileView from '../VibrationsProfile.vue'

/** Mount with the real i18n catalog + a fresh pinia. The shared assertion: no raw `inputShaping.*`
 *  key path leaks into the rendered output (which would mean a missing key or a broken <i18n-t>). */
function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

function noLeak(text: string): void {
  const leaked = text.match(/inputShaping\.[a-zA-Z]/)
  expect(leaked, leaked ? `leaked key: ${leaked[0]}` : '').toBeNull()
}

const vibResult: VibrationsProfile = {
  kinematics: 'corexy',
  accel: 3000,
  max_freq: 200,
  main_angles: [45, 135],
  segments_used: 40,
  segments_captured: 40,
  speeds: [20, 60, 100],
  energy_profile: [0.2, 1, 0.3],
  max_profile: [0.3, 1, 0.4],
  peak_speeds: [60],
  good_speed_ranges: [{ start: 80, end: 100, energy_pct: 20 }],
  angles: [0, 90, 180, 270],
  angle_energy: [0.5, 1, 0.5, 1],
  good_angle_ranges: [],
  symmetry_pct: 90,
  motor_freq: 55,
  motor_damping: 0.1,
  low_freq_warning: false,
  spectrogram: [[0.5]],
  recommended_speed: 90,
  verdict: 'ok',
}

describe('Input Shaping templates render through i18n (no leaked keys)', () => {
  it('InputShapingWidget — chrome + intro <i18n-t>', () => {
    const w = mount(InputShapingWidget, plugins())
    const text = w.text()
    noLeak(text)
    expect(text).toContain('Guided') // tab label
  })

  it('ResonanceFromPrinter — live tools + 3 <i18n-t> descriptions', () => {
    const w = mount(ResonanceFromPrinter, plugins())
    const text = w.text()
    noLeak(text)
    expect(text).toContain('Live tools')
  })

  it('VibrationsProfile — labels + interpolated values', () => {
    const w = mount(VibrationsProfileView, { props: { result: vibResult }, ...plugins() })
    const text = w.text()
    noLeak(text)
    expect(text).toContain('Vibrations profile')
  })

  it('ResonanceCompare — picker chrome', () => {
    const w = mount(ResonanceCompare, plugins())
    noLeak(w.text())
  })

  it('CsvSourceChooser — source tabs', () => {
    const w = mount(CsvSourceChooser, { props: { busy: false }, ...plugins() })
    const text = w.text()
    noLeak(text)
    expect(text).toContain('CSV source')
  })
})
