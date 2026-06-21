/** Structure for the Tuning wizards help layer. Translatable text lives in the i18n catalog under
 *  `tuning.help.*`; this module holds only the non-translatable structure. Rendered by the shared
 *  `HelpDrawer`.
 */

export type HelpIlloKey = 'tower' | 'apply' | 'retraction'

export type HelpTopic = 'overview' | 'workflow' | 'retraction' | 'glossary'

export const HELP_TOPICS: HelpTopic[] = ['overview', 'workflow', 'retraction', 'glossary']

export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  overview: 'tower',
  workflow: 'apply',
  retraction: 'retraction',
  glossary: 'tower',
}

export const GLOSSARY_KEYS = ['pressureAdvance', 'tuningTower', 'firmwareRetraction'] as const
export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
