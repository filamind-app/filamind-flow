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

/** The practical “how to read this” steps, shown once at the top of the dashboard. */
export const STEPS: string[] = [
  'Each card is one stepper driver — its heading is the axis (X / Y / Z / Extruder) and the badge is the chip model.',
  'Run current shows how hard the motor is driven; the live value may differ slightly from the configured “set” value — that’s normal.',
  'Mode tells you SpreadCycle (precise, louder) or StealthChop (quiet); microsteps shows how smooth the motion is.',
  'Home an axis or jog the motor to wake it — live temperature and fault flags only appear while a motor is enabled (idle drivers show “idle”).',
  'Open “advanced registers” on a card to inspect the raw tuning values the driver is using.',
]
