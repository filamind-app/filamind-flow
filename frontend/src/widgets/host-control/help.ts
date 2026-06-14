/** Structure for the Host Control help layer. Translatable text (titles, bodies, glossary) lives in
 *  the i18n catalog under `hostControl.help.*`; this module only holds non-translatable structure:
 *  which topics exist, their illustration, and the glossary term order. Rendered by `HelpNote.vue`
 *  behind a collapsed "ℹ what's this?" toggle — matching the other widgets' help pattern.
 */

export type HelpIlloKey = 'host' | 'monitor' | 'services'

export type HelpTopic = 'glossary' | 'monitor' | 'services'

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'host',
  monitor: 'monitor',
  services: 'services',
}

/** Glossary term keys, in display order. Text: `hostControl.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = [
  'host',
  'load',
  'swap',
  'throttle',
  'ntp',
  'locale',
  'service',
  'enabled',
  'mask',
] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
