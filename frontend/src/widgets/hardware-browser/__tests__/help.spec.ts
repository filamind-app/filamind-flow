import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS, type HelpIlloKey } from '../help'

const ILLO_KEYS: HelpIlloKey[] = ['search', 'category', 'chip']
const t = i18n.global.t as unknown as (key: string) => string
const te = i18n.global.te as unknown as (key: string) => boolean

describe('hardware-browser help structure + catalog', () => {
  it('has a title for every topic and a body for non-glossary topics', () => {
    for (const topic of HELP_TOPICS) {
      expect(te(`hardwareBrowser.help.topics.${topic}.title`), topic).toBe(true)
      expect(t(`hardwareBrowser.help.topics.${topic}.title`).length, topic).toBeGreaterThan(0)
      if (topic !== 'glossary') {
        expect(t(`hardwareBrowser.help.topics.${topic}.body`).length, topic).toBeGreaterThan(10)
      }
    }
  })

  it('any illo reference is a known illustration key', () => {
    for (const illo of Object.values(HELP_ILLO)) {
      expect(ILLO_KEYS).toContain(illo)
    }
  })

  it('the glossary defines each term with a term + def', () => {
    for (const k of GLOSSARY_KEYS) {
      expect(t(`hardwareBrowser.help.glossary.${k}.term`).length, k).toBeGreaterThan(0)
      expect(t(`hardwareBrowser.help.glossary.${k}.def`).length, k).toBeGreaterThan(10)
    }
  })
})
