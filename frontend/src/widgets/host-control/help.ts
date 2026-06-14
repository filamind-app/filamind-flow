/** Structure for the Host Control help layer. Translatable text (titles, bodies, glossary) lives in
 *  the i18n catalog under `hostControl.help.*`; this module only holds non-translatable structure:
 *  which topics exist (in order), their illustration, and the glossary term order. Rendered by the
 *  shared `HelpDrawer` — the adopted guide pattern across the app.
 */

export type HelpIlloKey = 'host' | 'monitor' | 'services' | 'cleanup' | 'system' | 'network'

export type HelpTopic = 'glossary' | 'monitor' | 'services' | 'cleanup' | 'system' | 'network'

/** Help topics in display order. Text: `hostControl.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'monitor',
  'services',
  'cleanup',
  'system',
  'network',
  'glossary',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'host',
  monitor: 'monitor',
  services: 'services',
  cleanup: 'cleanup',
  system: 'system',
  network: 'network',
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
