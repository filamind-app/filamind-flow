/** Structure for the Host Control help layer. Translatable text (titles, bodies, glossary) lives in
 *  the i18n catalog under `hostControl.help.*`; this module only holds non-translatable structure:
 *  which topics exist, their illustration, and the glossary term order. Rendered by `HelpNote.vue`
 *  behind a collapsed "ℹ what's this?" toggle — matching the other widgets' help pattern.
 */

export type HelpIlloKey = 'host' | 'monitor'

export type HelpTopic = 'glossary' | 'monitor'

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'host',
  monitor: 'monitor',
}

/** Glossary term keys, in display order. Text: `hostControl.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['host', 'load', 'swap', 'throttle', 'ntp', 'locale'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
