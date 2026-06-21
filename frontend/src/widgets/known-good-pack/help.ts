/** Structure for the Known-Good Pack help layer. Translatable text lives in the i18n catalog under
 *  `knownGoodPack.help.*`; this module holds only the non-translatable structure.
 */

export type HelpIlloKey = 'pack' | 'restore'

export type HelpTopic = 'overview' | 'restore' | 'glossary'

export const HELP_TOPICS: HelpTopic[] = ['overview', 'restore', 'glossary']

export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  overview: 'pack',
  restore: 'restore',
  glossary: 'pack',
}

export const GLOSSARY_KEYS = ['configPack', 'restorePoint'] as const
export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
