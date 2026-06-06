import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS, type HelpIlloKey } from '../help'
import HelpNote from '../HelpNote.vue'

const ILLO_KEYS: HelpIlloKey[] = ['mcu', 'flash', 'sync', 'tool']
const t = i18n.global.t as unknown as (key: string) => string
const te = i18n.global.te as unknown as (key: string) => boolean

describe('firmware help structure + catalog', () => {
  it('has a non-empty title + body in the catalog for every topic', () => {
    for (const topic of HELP_TOPICS) {
      expect(te(`firmware.help.topics.${topic}.title`), topic).toBe(true)
      expect(t(`firmware.help.topics.${topic}.title`).length, topic).toBeGreaterThan(0)
      expect(t(`firmware.help.topics.${topic}.body`).length, topic).toBeGreaterThan(10)
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
      expect(t(`firmware.help.glossary.${k}.term`).length, k).toBeGreaterThan(0)
      expect(t(`firmware.help.glossary.${k}.def`).length, k).toBeGreaterThan(10)
    }
    const terms = GLOSSARY_KEYS.map((k) => t(`firmware.help.glossary.${k}.term`).toLowerCase())
    expect(terms).toContain('mcu')
    expect(terms).toContain('flashing')
  })
})

describe('firmware HelpNote.vue (renders through i18n)', () => {
  it('shows the named title as the trigger, then the body when expanded', async () => {
    const w = mount(HelpNote, { props: { topic: 'overview' }, global: { plugins: [i18n] } })
    // The trigger is named (the topic title), not a generic "what's this?".
    expect(w.text()).toContain(t('firmware.help.topics.overview.title'))
    expect(w.text()).not.toContain(t('firmware.help.whatsThis'))
    await w.find('button').trigger('click')
    expect(w.text()).toContain(t('firmware.help.topics.overview.body'))
  })

  it('renders the glossary term list for the glossary topic', async () => {
    const w = mount(HelpNote, { props: { topic: 'glossary' }, global: { plugins: [i18n] } })
    await w.find('button').trigger('click')
    expect(w.text()).toContain(t('firmware.help.glossary.klipperFirmware.term'))
  })
})
