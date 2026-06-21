/** Structure for the Preflight help layer. Translatable text lives in the i18n catalog under
 *  `preflight.help.*`; this module holds only the non-translatable structure. Rendered by the
 *  shared `HelpDrawer`.
 */

export type HelpIlloKey = 'gate' | 'check'

export type HelpTopic = 'overview' | 'checks' | 'glossary'

export const HELP_TOPICS: HelpTopic[] = ['overview', 'checks', 'glossary']

export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  overview: 'gate',
  checks: 'check',
  glossary: 'gate',
}

export const GLOSSARY_KEYS = ['klippyState', 'homing'] as const
export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
