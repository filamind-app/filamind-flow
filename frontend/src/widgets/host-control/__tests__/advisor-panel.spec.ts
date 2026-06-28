import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

vi.mock('../api', () => ({
  fetchAdvisor: () =>
    Promise.resolve({
      cards: [
        {
          id: 'cpu',
          status: 'fail',
          score: 30,
          grade: 'F',
          badges: ['temp_high'],
          detail: '84 °C',
          fix_code: 'cpu_temp',
        },
        {
          id: 'disk',
          status: 'ok',
          score: 60,
          grade: 'C',
          badges: [],
          detail: '/ 40%',
          fix_code: null,
        },
      ],
    }),
}))

import AdvisorPanel from '../AdvisorPanel.vue'

describe('Host Control: Advisor panel', () => {
  it('renders graded cards with badges and fix hints', async () => {
    const w = mount(AdvisorPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain(i18n.global.t('hostControl.advisor.card.cpu'))
    expect(text).toContain('F') // grade letter
    expect(text).toContain('84 °C')
    expect(text).toContain(i18n.global.t('hostControl.advisor.badge.temp_high'))
    expect(text).toContain(i18n.global.t('hostControl.advisor.hint.cpu_temp'))
    // the clean disk card has no fix hint
    expect(text).toContain(i18n.global.t('hostControl.advisor.card.disk'))
  })
})
