/** Structure for the Firmware Upgrade widget's help layer. The translatable text (titles, bodies,
 *  glossary terms/defs) lives in the i18n catalog under `firmware.help.*`; this module only holds
 *  the non-translatable structure: which topics exist, their illustration, and the glossary term
 *  order. Rendered by `HelpNote.vue` behind a collapsed "ℹ what's this?" toggle.
 */

export type HelpIlloKey = 'mcu' | 'flash' | 'sync' | 'tool'

export type HelpTopic =
  | 'glossary'
  | 'overview'
  | 'guided'
  | 'status'
  | 'toolchain'
  | 'services'
  | 'devices'
  | 'configure'
  | 'external'
  | 'flash'

/** Every help topic, in display order. Text: `firmware.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'glossary',
  'overview',
  'guided',
  'status',
  'toolchain',
  'services',
  'devices',
  'configure',
  'external',
  'flash',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'mcu',
  overview: 'flash',
  guided: 'flash',
  status: 'sync',
  toolchain: 'tool',
  services: 'tool',
  devices: 'flash',
  configure: 'tool',
  external: 'flash',
  flash: 'flash',
}

/** Glossary term keys, in display order. Text: `firmware.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = [
  'klipperFirmware',
  'mcu',
  'hostMcuSync',
  'katapultDfu',
  'flashing',
  'profile',
] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]

/** The practical build→flash quick guide, shown once at the top. */
export const STEPS: string[] = [
  'Check each MCU’s version against the host — a ⚠ badge flags firmware that’s out of sync.',
  'Configure a board’s firmware (Configure →) and save it as a profile, so it rebuilds identically.',
  'Build the firmware for that profile and watch the live log for errors.',
  'Put the board in its bootloader (Katapult / DFU) if needed, then Flash — Klipper is stopped and restarted around it.',
  'After flashing, the board re-enumerates and its version updates here — confirm it now matches the host.',
]
