// Help content map for the Control widget's shared <HelpDrawer>. Titles/bodies live in the
// `control.help.topics.*` i18n keys; this just declares the topic order + which glyph each uses.
export const HELP_TOPICS = ['job', 'temps', 'motion', 'webcam'] as const

export const HELP_ILLO: Partial<Record<string, string>> = {
  job: 'job',
  temps: 'temps',
  motion: 'motion',
  webcam: 'webcam',
}

// No glossary for this widget yet (the drawer renders the topics above).
export const GLOSSARY_KEYS: readonly string[] = []
