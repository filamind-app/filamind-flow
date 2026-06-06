// Type-safe message keys. The `en` catalog is the single source of truth: each namespace JSON
// contributes its top-level key, and intersecting them gives the full schema. With this, `t('…')`
// is autocompleted and a wrong key fails `npm run type-check` (vue-tsc). Other locales are checked
// *structurally* against `en` by `npm run i18n:keydiff` (the eslint no-unused-keys rule is
// unreliable here because keys are built dynamically, e.g. `t('…verdict.' + letter)`).

import type boardTopology from '@/locales/en/board-topology.json'
import type common from '@/locales/en/common.json'
import type configEditor from '@/locales/en/config-editor.json'
import type firmware from '@/locales/en/firmware.json'
import type inputShaping from '@/locales/en/input-shaping.json'
import type maxFlow from '@/locales/en/max-flow.json'
import type motorDrivers from '@/locales/en/motor-drivers.json'
import type shell from '@/locales/en/shell.json'

type MessageSchema = typeof common &
  typeof shell &
  typeof firmware &
  typeof inputShaping &
  typeof motorDrivers &
  typeof configEditor &
  typeof maxFlow &
  typeof boardTopology

declare module 'vue-i18n' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface DefineLocaleMessage extends MessageSchema {}
}
