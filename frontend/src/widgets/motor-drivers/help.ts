/** Structure for the Motor Drivers widget's help layer. The translatable text (titles, bodies,
 *  glossary terms/defs) lives in the i18n catalog under `motorDrivers.help.*`; this module only
 *  holds the non-translatable structure: which topics exist, their illustration, and the glossary
 *  term order. Rendered by `HelpNote.vue` behind a collapsed "ℹ what's this?" toggle.
 */

export type HelpIlloKey =
  | 'driver'
  | 'current'
  | 'chopper'
  | 'microsteps'
  | 'stallguard'
  | 'homing'
  | 'coolstep'

export type HelpTopic =
  | 'glossary'
  | 'overview'
  | 'current'
  | 'chopper'
  | 'microsteps'
  | 'stallguard'
  | 'health'
  | 'temperature'
  | 'catalog'
  | 'motor'
  | 'recommend'
  | 'homing'
  | 'sensorless'
  | 'monitor'
  | 'motorsync'
  | 'registers'
  | 'coolstep'

/** Every help topic, in display order. Text: `motorDrivers.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'glossary',
  'overview',
  'current',
  'chopper',
  'microsteps',
  'stallguard',
  'health',
  'temperature',
  'catalog',
  'motor',
  'motorsync',
  'monitor',
  'homing',
  'sensorless',
  'coolstep',
  'registers',
  'recommend',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'driver',
  overview: 'driver',
  current: 'current',
  chopper: 'chopper',
  microsteps: 'microsteps',
  stallguard: 'stallguard',
  health: 'driver',
  temperature: 'current',
  catalog: 'driver',
  motor: 'current',
  motorsync: 'driver',
  monitor: 'driver',
  homing: 'homing',
  sensorless: 'stallguard',
  coolstep: 'coolstep',
  registers: 'chopper',
  recommend: 'driver',
}

/** Glossary term keys, in display order. Text: `motorDrivers.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = [
  'tmcDriver',
  'runCurrent',
  'holdCurrent',
  'microsteps',
  'stealthChop',
  'spreadCycle',
  'stallGuard',
  'senseResistor',
  'interface',
] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
