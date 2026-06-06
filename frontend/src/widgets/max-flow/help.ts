/** Help-layer structure for the Max-Flow widget. Translatable text lives in the i18n catalog
 *  under `maxFlow.help.*`; this only holds the non-translatable structure (topic order, each
 *  topic's illustration, glossary order). Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'flow' | 'stallguard' | 'slip' | 'safety'

export type HelpTopic = 'glossary' | 'howItWorks' | 'stallguard' | 'safety' | 'slicer'

/** Help topics in display order. Text: `maxFlow.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['glossary', 'howItWorks', 'stallguard', 'safety', 'slicer']

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'flow',
  howItWorks: 'flow',
  stallguard: 'stallguard',
  safety: 'safety',
  slicer: 'flow',
}

/** Glossary term keys in display order. Text: `maxFlow.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['flow', 'stallguard', 'slip', 'meltzone'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
