import { describe, expect, it } from 'vitest'

import { GLOSSARY, HELP, type HelpIlloKey, type HelpTopic } from '../help'

const TOPICS: HelpTopic[] = [
  'glossary',
  'analyze',
  'grade',
  'diagnostics',
  'chart',
  'shapers',
  'config',
  'noise',
  'belts',
  'axesMap',
  'sustain',
  'vibrations',
  'guided',
  'history',
]

const ILLO_KEYS: HelpIlloKey[] = ['flow', 'peak', 'shaper', 'noise', 'belt', 'sensor', 'sweep']

describe('help', () => {
  it('has an entry with a title for every topic', () => {
    for (const topic of TOPICS) {
      expect(HELP[topic], topic).toBeDefined()
      expect(HELP[topic].title.length, topic).toBeGreaterThan(0)
    }
  })

  it('every topic except glossary has a body', () => {
    for (const topic of TOPICS) {
      if (topic === 'glossary') continue
      expect(HELP[topic].body.length, topic).toBeGreaterThan(10)
    }
  })

  it('any illo reference is a known illustration key', () => {
    for (const topic of TOPICS) {
      const illo = HELP[topic].illo
      if (illo) expect(ILLO_KEYS, topic).toContain(illo)
    }
  })

  it('the glossary defines the core terms', () => {
    expect(GLOSSARY.length).toBeGreaterThanOrEqual(6)
    for (const t of GLOSSARY) {
      expect(t.term.length).toBeGreaterThan(0)
      expect(t.def.length).toBeGreaterThan(10)
    }
    const terms = GLOSSARY.map((t) => t.term.toLowerCase())
    expect(terms).toContain('input shaper')
    expect(terms).toContain('resonance')
  })
})
