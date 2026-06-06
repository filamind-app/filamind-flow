/** Help-layer structure for the Macro Designer. Translatable text lives in the i18n catalog
 *  under `macroDesigner.help.*`; this only holds the non-translatable structure (topic order,
 *  each topic's illustration, glossary order). Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'path' | 'gcode' | 'macro'

export type HelpTopic = 'glossary' | 'simulator' | 'motion' | 'macros'

/** Help topics in display order. Text: `macroDesigner.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['glossary', 'simulator', 'motion', 'macros']

/** The illustration each topic shows (identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'gcode',
  simulator: 'path',
  motion: 'path',
  macros: 'macro',
}

/** Glossary term keys in display order. Text: `macroDesigner.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['gcode', 'feedrate', 'macro'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
