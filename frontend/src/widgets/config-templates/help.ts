/** Help-layer structure for the Config Templates widget. Translatable text lives in the i18n
 *  catalog under `configTemplates.help.*`; this only holds the non-translatable structure
 *  (topic order, each topic's illustration, glossary order). Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'template' | 'paste' | 'section'

export type HelpTopic = 'glossary' | 'what' | 'insert' | 'sections'

/** Help topics in display order. Text: `configTemplates.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['glossary', 'what', 'insert', 'sections']

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'template',
  what: 'template',
  insert: 'paste',
  sections: 'section',
}

/** Glossary term keys in display order. Text: `configTemplates.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['template', 'macro', 'section'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
