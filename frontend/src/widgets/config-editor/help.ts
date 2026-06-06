/** Help-layer structure for the Config Editor widget. The translatable text (topic titles /
 *  bodies, glossary terms / defs, "how to use" steps) lives in the i18n catalog under
 *  `configEditor.help.*`; this module only holds the non-translatable structure: which topics
 *  exist, their illustration, and the glossary term order. Rendered by the shared `HelpDrawer`.
 */

export type HelpIlloKey = 'file' | 'section' | 'include' | 'validation' | 'saveConfig'

export type HelpTopic =
  | 'glossary'
  | 'sections'
  | 'includes'
  | 'validation'
  | 'saveConfig'
  | 'readonly'

/** Every help topic, in display order. Text: `configEditor.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'glossary',
  'sections',
  'includes',
  'validation',
  'saveConfig',
  'readonly',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'file',
  sections: 'section',
  includes: 'include',
  validation: 'validation',
  saveConfig: 'saveConfig',
  readonly: 'file',
}

/** Glossary term keys, in display order. Text: `configEditor.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = ['section', 'parameter', 'include', 'saveConfig'] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
