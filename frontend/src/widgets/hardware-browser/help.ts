/** Help-layer structure for the Hardware Browser. Translatable text lives in the i18n catalog
 *  under `hardwareBrowser.help.*`; this only holds the non-translatable structure (topic order,
 *  each topic's illustration, glossary order). Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'search' | 'category' | 'chip'

export type HelpTopic = 'glossary' | 'search' | 'categories' | 'manufacturers' | 'relationships'

/** Help topics in display order. Text: `hardwareBrowser.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'glossary',
  'search',
  'categories',
  'relationships',
  'manufacturers',
]

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'chip',
  search: 'search',
  categories: 'category',
  relationships: 'chip',
  manufacturers: 'chip',
}

/** Glossary term keys in display order. Text: `hardwareBrowser.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['category', 'manufacturer', 'spec', 'links'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
