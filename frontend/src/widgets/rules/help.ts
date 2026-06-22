/** Structure for the Rules help layer. Translatable text lives under `rules.help.*`. */

export type HelpIlloKey = 'rule' | 'safe'

export type HelpTopic = 'overview' | 'safety' | 'glossary'

export const HELP_TOPICS: HelpTopic[] = ['overview', 'safety', 'glossary']

export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  overview: 'rule',
  safety: 'safe',
  glossary: 'rule',
}

export const GLOSSARY_KEYS = ['trigger', 'action', 'armed'] as const
export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
