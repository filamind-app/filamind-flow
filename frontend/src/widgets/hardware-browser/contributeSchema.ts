/** Declarative schemas for the "Suggest a part" forms.
 *
 *  Each part type lists its fields (with the JSON key + control type + optional unit/group), and a
 *  builder assembles a catalog-shaped JSON fragment from the entered values. The fragment is what a
 *  user submits as a GitHub issue for review; a maintainer merges it into the catalog (see
 *  scripts/apply_submission.py). Field LABELS are resolved by the dialog from i18n
 *  (`hardwareBrowser.suggest.f.<key>`), so this file holds only structure, never copy. */

export type FieldType = 'text' | 'number' | 'textarea' | 'select' | 'checkbox'

/** Where a field lands in the assembled JSON: a top-level key, or nested under a sub-object. */
export type FieldGroup = 'top' | 'autotune' | 'caps' | 'maxFlow' | 'preset'

export interface FieldDef {
  /** JSON key (also the i18n label suffix). */
  key: string
  type: FieldType
  required?: boolean
  /** Options for a select control (values are stored verbatim). */
  options?: string[]
  /** A Latin unit shown after the label (kept untranslated, e.g. 'Ω', 'mH', 'mm³/s'). */
  unit?: string
  /** Sub-object this field nests into; omit for a top-level key. */
  group?: FieldGroup
}

export type PartType = 'motor' | 'driver' | 'hotend' | 'host' | 'manufacturer' | 'board' | 'catalog'

export interface PartTypeDef {
  type: PartType
  icon: string
  /** The catalog entity's id key, derived from manufacturer+name (manufacturers carry no id). */
  idKey?: string
  fields: FieldDef[]
  /** Show a free-form key/value "specs" editor. */
  hasSpecs?: boolean
  /** Show a copyable Klipper config snippet textarea. */
  hasConfig?: boolean
  /** Boards only: a repeatable ports editor (each port carries a signal→pin map). */
  hasPorts?: boolean
  /** Fixed fields merged into every fragment of this type (e.g. a catalog category). */
  fixed?: Record<string, unknown>
}

const BOARD_CLASSES = ['mainboard', 'toolhead', 'expansion', 'host', 'other']
const HOST_KINDS = ['sbc', 'x86', 'mainboard', 'locked', 'other']
const STEPS_PER_REV = ['200', '400']

export const PART_TYPES: PartTypeDef[] = [
  {
    type: 'motor',
    icon: '🔩',
    idKey: 'motor_id',
    hasSpecs: true,
    hasConfig: true,
    fields: [
      { key: 'manufacturer', type: 'text', required: true },
      { key: 'name', type: 'text', required: true },
      { key: 'nema', type: 'text' },
      { key: 'stepAngle', type: 'text', unit: '°' },
      { key: 'ratedCurrent', type: 'number', unit: 'A' },
      { key: 'holdingTorque', type: 'number', unit: 'N·m' },
      { key: 'recommendedRunCurrent', type: 'number', unit: 'A' },
      // autotune (electrical model)
      { key: 'resistance_ohm', type: 'number', unit: 'Ω', group: 'autotune' },
      { key: 'inductance_H', type: 'number', unit: 'H', group: 'autotune' },
      { key: 'holding_torque_Nm', type: 'number', unit: 'N·m', group: 'autotune' },
      { key: 'max_current_A', type: 'number', unit: 'A', group: 'autotune' },
      { key: 'steps_per_rev', type: 'select', options: STEPS_PER_REV, group: 'autotune' },
    ],
  },
  {
    type: 'driver',
    icon: '⚡',
    idKey: 'driver_id',
    hasSpecs: true,
    hasConfig: true,
    fields: [
      { key: 'manufacturer', type: 'text', required: true },
      { key: 'name', type: 'text', required: true },
      { key: 'chip', type: 'text' },
      { key: 'interface', type: 'text' },
      { key: 'klipperSection', type: 'text' },
      { key: 'sensorless', type: 'checkbox' },
      // caps (capability map)
      { key: 'max_current_a', type: 'number', unit: 'A', group: 'caps' },
      { key: 'microsteps', type: 'number', group: 'caps' },
      { key: 'stealthchop', type: 'checkbox', group: 'caps' },
      { key: 'spreadcycle', type: 'checkbox', group: 'caps' },
      { key: 'coolstep', type: 'checkbox', group: 'caps' },
      { key: 'stallguard', type: 'checkbox', group: 'caps' },
      { key: 'stallguard_field', type: 'text', group: 'caps' },
    ],
  },
  {
    type: 'hotend',
    icon: '🔥',
    idKey: 'catalog_id',
    hasSpecs: true,
    fixed: { category: 'Hotends & Heaters', subsection: 'Hotends' },
    fields: [
      { key: 'manufacturer', type: 'text', required: true },
      { key: 'name', type: 'text', required: true },
      { key: 'max_temp_c', type: 'number', unit: '°C', group: 'maxFlow' },
      { key: 'suggested_temp_c', type: 'number', unit: '°C', group: 'maxFlow' },
      { key: 'expected_max_flow_mm3s', type: 'number', unit: 'mm³/s', group: 'maxFlow' },
      { key: 'melt_zone_mm', type: 'number', unit: 'mm', group: 'maxFlow' },
      { key: 'START', type: 'number', unit: 'mm³/s', group: 'preset' },
      { key: 'MAX', type: 'number', unit: 'mm³/s', group: 'preset' },
      { key: 'COARSE_STEP', type: 'number', unit: 'mm³/s', group: 'preset' },
    ],
  },
  {
    type: 'host',
    icon: '🖥',
    idKey: 'host_id',
    hasSpecs: true,
    hasConfig: true,
    fields: [
      { key: 'manufacturer', type: 'text', required: true },
      { key: 'name', type: 'text', required: true },
      { key: 'kind', type: 'select', options: HOST_KINDS },
      { key: 'soc', type: 'text' },
      { key: 'cpu', type: 'text' },
      { key: 'ram', type: 'text' },
      { key: 'klipperOpen', type: 'checkbox' },
    ],
  },
  {
    type: 'manufacturer',
    icon: '🏭',
    fields: [
      { key: 'name', type: 'text', required: true },
      { key: 'country', type: 'text' },
      { key: 'website', type: 'text' },
      { key: 'specialty', type: 'text' },
    ],
  },
  {
    type: 'board',
    icon: '🧩',
    idKey: 'board_id',
    hasSpecs: true,
    hasConfig: true,
    hasPorts: true,
    fields: [
      { key: 'manufacturer', type: 'text', required: true },
      { key: 'model', type: 'text', required: true },
      { key: 'display_name', type: 'text' },
      { key: 'boardClass', type: 'select', options: BOARD_CLASSES },
      { key: 'mcu', type: 'text' },
      { key: 'clock', type: 'text' },
      { key: 'voltage', type: 'text' },
      { key: 'driver_slots', type: 'number' },
      { key: 'usb', type: 'text' },
      { key: 'can', type: 'text' },
      { key: 'ethernet', type: 'text' },
    ],
  },
  {
    type: 'catalog',
    icon: '📦',
    idKey: 'catalog_id',
    hasSpecs: true,
    hasConfig: true,
    fields: [
      { key: 'category', type: 'text', required: true },
      { key: 'subsection', type: 'text' },
      { key: 'manufacturer', type: 'text' },
      { key: 'name', type: 'text', required: true },
    ],
  },
]

export function typeDef(type: PartType): PartTypeDef {
  return PART_TYPES.find((p) => p.type === type) ?? PART_TYPES[0]
}

/** A URL/JSON-safe slug from free text (lowercase, hyphen-separated, ascii-ish). */
export function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

/** Board "specs" use Title-Case keys in the catalog; map our field keys to them. */
const BOARD_SPEC_KEY: Record<string, string> = {
  mcu: 'MCU',
  clock: 'Clock',
  voltage: 'Voltage',
  driver_slots: 'Driver slots',
  usb: 'USB',
  can: 'CAN',
  ethernet: 'Ethernet',
}

export interface PortEntry {
  label: string
  category: string
  portFunction: string
  pinMap: { signal: string; pin: string }[]
}

export interface FragmentInput {
  values: Record<string, string | boolean>
  specs: { key: string; value: string }[]
  ports: PortEntry[]
  configSnippet: string
}

function num(v: unknown): number | string | undefined {
  if (v === '' || v == null) return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : String(v)
}

/** Assemble a catalog-shaped JSON fragment for the given part type. Empty fields are omitted. */
export function buildFragment(type: PartType, input: FragmentInput): Record<string, unknown> {
  const def = typeDef(type)
  const v = input.values
  const out: Record<string, unknown> = {}
  const groups: Record<string, Record<string, unknown>> = {}

  // id slug (manufacturers carry none)
  if (def.idKey) {
    const base =
      type === 'board'
        ? `${v.manufacturer ?? ''} ${v.model ?? ''}`
        : `${v.manufacturer ?? ''} ${v.name ?? ''}`
    const slug = slugify(String(base))
    if (slug) out[def.idKey] = slug
  }

  for (const f of def.fields) {
    const raw = v[f.key]
    // Omit empties and unchecked booleans — only `true` checkboxes and non-empty values are kept.
    if (raw === '' || raw == null || raw === false) continue
    const value = f.type === 'number' ? num(raw) : raw
    if (value === undefined) continue
    if (f.group && f.group !== 'top') {
      groups[f.group] = groups[f.group] ?? {}
      groups[f.group][f.key] = value
    } else if (type === 'board' && BOARD_SPEC_KEY[f.key]) {
      // board headline specs live under specs{}
      groups.specs = groups.specs ?? {}
      groups.specs[BOARD_SPEC_KEY[f.key]] = value
    } else {
      out[f.key] = value
    }
  }

  // free-form specs editor
  const specs: Record<string, string> = (groups.specs as Record<string, string>) ?? {}
  for (const s of input.specs) {
    if (s.key.trim()) specs[s.key.trim()] = s.value
  }
  if (Object.keys(specs).length) out.specs = specs

  // nested sub-objects (autotune / caps / maxFlow with its preset)
  if (groups.autotune) out.autotune = groups.autotune
  if (groups.caps) {
    // mirror sensorless into caps for completeness
    if (v.sensorless === true) (groups.caps as Record<string, unknown>).sensorless = true
    out.caps = groups.caps
  }
  if (groups.maxFlow || groups.preset) {
    const maxFlow: Record<string, unknown> = { ...(groups.maxFlow ?? {}) }
    if (groups.preset) maxFlow.preset = groups.preset
    maxFlow.source = 'community-submission'
    out.maxFlow = maxFlow
  }

  // boards: ports with pin maps
  if (def.hasPorts && input.ports.length) {
    const ports = input.ports
      .filter((p) => p.label.trim() || p.pinMap.some((m) => m.signal.trim() || m.pin.trim()))
      .map((p) => {
        const port: Record<string, unknown> = {}
        if (p.label.trim()) port.label = p.label.trim()
        if (p.category.trim()) port.category = p.category.trim()
        if (p.portFunction.trim()) port.portFunction = p.portFunction.trim()
        const pinMap = p.pinMap
          .filter((m) => m.signal.trim() && m.pin.trim())
          .map((m) => ({ signal: m.signal.trim(), pin: m.pin.trim() }))
        if (pinMap.length) port.pinMap = pinMap
        return port
      })
    if (ports.length) out.ports = ports
  }

  if (def.hasConfig && input.configSnippet.trim()) out.configSnippet = input.configSnippet.trim()
  if (def.fixed) Object.assign(out, def.fixed)
  return out
}
