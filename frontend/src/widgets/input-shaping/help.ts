/** Structure for the Input Shaping widget's help layer. The translatable text (titles, bodies,
 *  glossary terms/defs) lives in the i18n catalog under `inputShaping.help.*`; this module only
 *  holds the non-translatable structure: which topics exist, their illustration, and the glossary
 *  term order. Rendered by `HelpNote.vue` behind a collapsed "ℹ what's this?" toggle.
 */

export type HelpIlloKey = 'flow' | 'peak' | 'shaper' | 'noise' | 'belt' | 'sensor' | 'sweep'

export type HelpTopic =
  | 'glossary'
  | 'analyze'
  | 'grade'
  | 'diagnostics'
  | 'chart'
  | 'shapers'
  | 'config'
  | 'noise'
  | 'belts'
  | 'axesMap'
  | 'sustain'
  | 'vibrations'
  | 'guided'
  | 'history'

/** Every help topic, in display order. Text: `inputShaping.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'glossary',
  'analyze',
  'grade',
  'diagnostics',
  'chart',
  'shapers',
  'config',
  'noise',
  'belts',
  'axesMap',
  'sustain',
  'vibrations',
  'guided',
  'history',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  analyze: 'flow',
  chart: 'peak',
  shapers: 'shaper',
  noise: 'noise',
  belts: 'belt',
  axesMap: 'sensor',
  vibrations: 'sweep',
  guided: 'flow',
}

/** Glossary term keys, in display order. Text: `inputShaping.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = [
  'inputShaper',
  'resonance',
  'psd',
  'smoothing',
  'vibrationPct',
  'maxAccel',
] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
