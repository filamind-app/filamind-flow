/** Help-layer structure for the Board Topology widget. Translatable text lives in the i18n
 *  catalog under `boardTopology.help.*`; this only holds the non-translatable structure
 *  (topic order, each topic's illustration, glossary order). Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'host' | 'mcu' | 'canbus'

export type HelpTopic = 'glossary' | 'mcus' | 'connections' | 'detection'

/** Help topics in display order. Text: `boardTopology.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['glossary', 'mcus', 'connections', 'detection']

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'host',
  mcus: 'mcu',
  connections: 'canbus',
  detection: 'mcu',
}

/** Glossary term keys in display order. Text: `boardTopology.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['mcu', 'canbus', 'host'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
