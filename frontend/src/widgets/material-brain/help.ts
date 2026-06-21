/** Structure for the Material Brain help layer. Translatable text (titles, bodies, glossary) lives
 *  in the i18n catalog under `material.help.*`; this module holds only non-translatable structure:
 *  which topics exist (in order), their illustration, and the glossary term order. Rendered by the
 *  shared `HelpDrawer` - the adopted guide pattern across the app.
 */

export type HelpIlloKey = 'material' | 'flow'

export type HelpTopic = 'overview' | 'flow' | 'glossary'

/** Help topics in display order. Text: `material.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = ['overview', 'flow', 'glossary']

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  overview: 'material',
  flow: 'flow',
  glossary: 'material',
}

/** Glossary term order. Text: `material.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['volumetricFlow', 'density', 'ceiling'] as const
export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
