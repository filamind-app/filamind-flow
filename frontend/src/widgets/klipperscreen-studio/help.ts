/** Structure for the KlipperScreen Studio help layer. The translatable text (titles, bodies,
 *  glossary terms/defs) lives in the i18n catalog under `klipperscreenStudio.help.*`; this module
 *  only holds the non-translatable structure: which topics exist (in order), their illustration,
 *  and the glossary term order. Rendered by the shared `HelpDrawer` — the adopted guide pattern.
 */

export type HelpIlloKey = 'screen' | 'config' | 'settings' | 'menu' | 'theme' | 'kiosk'

export type HelpTopic = 'glossary' | 'config' | 'settings' | 'menus' | 'themes' | 'kiosk'

/** Help topics in display order. Text: `klipperscreenStudio.help.topics.<topic>.{title,body}`. */
export const HELP_TOPICS: HelpTopic[] = [
  'config',
  'settings',
  'menus',
  'themes',
  'kiosk',
  'glossary',
]

/** The illustration each topic shows (illustration keys are identifiers, not translated). */
export const HELP_ILLO: Partial<Record<HelpTopic, HelpIlloKey>> = {
  glossary: 'screen',
  config: 'config',
  settings: 'settings',
  menus: 'menu',
  themes: 'theme',
  kiosk: 'kiosk',
}

/** Glossary term keys, in display order. Text: `klipperscreenStudio.help.glossary.<key>.{term,def}`. */
export const GLOSSARY_KEYS = [
  'klipperScreen',
  'theme',
  'menu',
  'panel',
  'autoBlock',
  'kiosk',
] as const

export type GlossaryKey = (typeof GLOSSARY_KEYS)[number]
