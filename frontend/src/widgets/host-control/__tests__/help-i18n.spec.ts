import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import { GLOSSARY_KEYS, HELP_TOPICS } from '../help'

/** The Host Control HelpDrawer builds its keys from help.ts at runtime, so a topic/glossary entry
 *  listed there but missing from the i18n catalog would render a raw key. Lock the two together,
 *  and verify the new CAN-bus help (topics + glossary + the panel's reading-based hints) resolves. */
describe('Host Control: help i18n is complete', () => {
  const te = i18n.global.te
  const t = i18n.global.t

  it('has a title + body for every help topic', () => {
    // 'glossary' is the special glossary section (rendered separately), not a title/body topic.
    for (const topic of HELP_TOPICS.filter((tp) => tp !== 'glossary')) {
      expect(te(`hostControl.help.topics.${topic}.title`), `${topic}.title`).toBe(true)
      expect(te(`hostControl.help.topics.${topic}.body`), `${topic}.body`).toBe(true)
    }
  })

  it('has a term + def for every glossary key', () => {
    for (const k of GLOSSARY_KEYS) {
      expect(te(`hostControl.help.glossary.${k}.term`), `${k}.term`).toBe(true)
      expect(te(`hostControl.help.glossary.${k}.def`), `${k}.def`).toBe(true)
    }
  })

  it('covers the CAN-bus help topics + glossary + panel hints', () => {
    for (const topic of ['canbus', 'canParams', 'canTermination'])
      expect(HELP_TOPICS).toContain(topic)
    for (const k of ['canbus', 'uuid', 'bitrate', 'samplePoint', 'termination', 'busoff'])
      expect(GLOSSARY_KEYS).toContain(k)
    // The reading-based bitrate warning must keep its firmware-match caveat.
    expect(t('hostControl.canbus.confirmBitrate')).toMatch(/firmware/i)
    for (const k of ['advancedTip', 'flagsWarn'])
      expect(te(`hostControl.canbus.${k}`), k).toBe(true)
  })
})
