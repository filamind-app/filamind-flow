import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS, type HelpIlloKey } from '../help'
import HelpNote from '../HelpNote.vue'

const ILLO_KEYS: HelpIlloKey[] = [
  'driver',
  'current',
  'chopper',
  'microsteps',
  'stallguard',
  'homing',
  'coolstep',
]
const t = i18n.global.t as unknown as (key: string) => string
const te = i18n.global.te as unknown as (key: string) => boolean

describe('motor-drivers help structure + catalog', () => {
  it('has a non-empty title + body in the catalog for every topic', () => {
    for (const topic of HELP_TOPICS) {
      expect(te(`motorDrivers.help.topics.${topic}.title`), topic).toBe(true)
      expect(t(`motorDrivers.help.topics.${topic}.title`).length, topic).toBeGreaterThan(0)
      expect(t(`motorDrivers.help.topics.${topic}.body`).length, topic).toBeGreaterThan(10)
    }
  })

  it('any illo reference is a known illustration key', () => {
    for (const illo of Object.values(HELP_ILLO)) {
      expect(ILLO_KEYS).toContain(illo)
    }
  })

  it('the glossary defines the core terms with a term + def each', () => {
    expect(GLOSSARY_KEYS.length).toBeGreaterThanOrEqual(9)
    for (const k of GLOSSARY_KEYS) {
      expect(t(`motorDrivers.help.glossary.${k}.term`).length, k).toBeGreaterThan(0)
      expect(t(`motorDrivers.help.glossary.${k}.def`).length, k).toBeGreaterThan(10)
    }
    const terms = GLOSSARY_KEYS.map((k) => t(`motorDrivers.help.glossary.${k}.term`).toLowerCase())
    expect(terms).toContain('tmc driver')
    expect(terms).toContain('run current')
  })
})

describe('motor-drivers HelpNote.vue (renders through i18n)', () => {
  it('shows the toggle, then title + body when expanded', async () => {
    const w = mount(HelpNote, { props: { topic: 'overview' }, global: { plugins: [i18n] } })
    expect(w.text()).toContain(t('motorDrivers.help.whatsThis'))
    await w.find('button').trigger('click')
    expect(w.text()).toContain(t('motorDrivers.help.topics.overview.title'))
    expect(w.text()).toContain(t('motorDrivers.help.topics.overview.body'))
  })

  it('renders the glossary term list for the glossary topic', async () => {
    const w = mount(HelpNote, { props: { topic: 'glossary' }, global: { plugins: [i18n] } })
    await w.find('button').trigger('click')
    expect(w.text()).toContain(t('motorDrivers.help.glossary.tmcDriver.term'))
  })
})
