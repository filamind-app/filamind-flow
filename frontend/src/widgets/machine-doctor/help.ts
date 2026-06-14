/** Help-layer structure for the Machine Doctor widget. Translatable text lives in the i18n catalog
 *  under `machineDoctor.help.*`; this only holds the non-translatable structure (topic order, each
 *  topic's illustration, glossary order). Rendered by the shared `HelpDrawer` — the adopted pattern.
 */

export type HelpIlloKey = 'doctor' | 'grade' | 'fix'

export type HelpTopic = 'glossary' | 'scan' | 'grade' | 'fixes'

/** Help topics in display order. Text: `machineDoctor.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['scan', 'grade', 'fixes', 'glossary']

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'doctor',
  scan: 'doctor',
  grade: 'grade',
  fixes: 'fix',
}

/** Glossary term keys in display order. Text: `machineDoctor.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['grade', 'pillar', 'finding'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
