import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS, type HelpIlloKey } from '../help'
import HelpNote from '../HelpNote.vue'

const ILLO_KEYS: HelpIlloKey[] = ['flow', 'peak', 'shaper', 'noise', 'belt', 'sensor', 'sweep']
const t = i18n.global.t as unknown as (key: string) => string
const te = i18n.global.te as unknown as (key: string) => boolean

describe('help structure + catalog', () => {
  it('has a non-empty title in the catalog for every topic', () => {
    for (const topic of HELP_TOPICS) {
      const key = `inputShaping.help.topics.${topic}.title`
      expect(te(key), topic).toBe(true)
      expect(t(key).length, topic).toBeGreaterThan(0)
    }
  })

  it('every topic except glossary has a body', () => {
    for (const topic of HELP_TOPICS) {
      if (topic === 'glossary') continue
      const key = `inputShaping.help.topics.${topic}.body`
      expect(te(key), topic).toBe(true)
      expect(t(key).length, topic).toBeGreaterThan(10)
    }
  })

  it('any illo reference is a known illustration key', () => {
    for (const illo of Object.values(HELP_ILLO)) {
      expect(ILLO_KEYS).toContain(illo)
    }
  })

  it('the glossary defines the core terms with a term + def each', () => {
    expect(GLOSSARY_KEYS.length).toBeGreaterThanOrEqual(6)
    for (const k of GLOSSARY_KEYS) {
      expect(t(`inputShaping.help.glossary.${k}.term`).length, k).toBeGreaterThan(0)
      expect(t(`inputShaping.help.glossary.${k}.def`).length, k).toBeGreaterThan(10)
    }
    const terms = GLOSSARY_KEYS.map((k) => t(`inputShaping.help.glossary.${k}.term`).toLowerCase())
    expect(terms).toContain('input shaper')
    expect(terms).toContain('resonance')
  })
})

describe('HelpNote.vue (renders through i18n)', () => {
  it('shows the toggle, then the title + body when expanded', async () => {
    const wrapper = mount(HelpNote, { props: { topic: 'analyze' }, global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain(t('inputShaping.help.whatsThis'))
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain(t('inputShaping.help.topics.analyze.title'))
    expect(wrapper.text()).toContain(t('inputShaping.help.topics.analyze.body'))
  })

  it('renders the glossary term list for the glossary topic', async () => {
    const wrapper = mount(HelpNote, { props: { topic: 'glossary' }, global: { plugins: [i18n] } })
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain(t('inputShaping.help.glossary.inputShaper.term'))
  })
})
