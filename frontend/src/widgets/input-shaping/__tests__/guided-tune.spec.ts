import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import GuidedTune from '../GuidedTune.vue'

describe('GuidedTune.vue (renders through i18n)', () => {
  it('renders the step rail and the active step from the catalog (no raw keys leak)', () => {
    const wrapper = mount(GuidedTune, { global: { plugins: [i18n] } })
    const text = wrapper.text()
    expect(text).toContain('Guided tune') // ui.title
    expect(text).toContain('Noise') // steps.noise.label (rail)
    expect(text).toContain('Belts') // steps.belts.label (rail)
    expect(text).toContain('Accelerometer noise') // steps.noise.title (active step)
    expect(text).toContain('Confirm the sensor is mounted solidly') // steps.noise.why
    // Any unresolved key would render its dotted path — guard against that.
    expect(text).not.toContain('inputShaping.guided')
  })
})
