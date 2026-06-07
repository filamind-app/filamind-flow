/** Shapes returned by the Hardware Browser endpoints (`/api/hardware*`). */

export interface HardwareItem {
  category: string
  subsection: string
  manufacturer: string
  name: string
  specs: Record<string, string>
}

export interface HardwareSearchResult {
  total: number
  count: number
  offset: number
  limit: number
  items: HardwareItem[]
}

export interface HardwareCategories {
  categories: string[]
  counts?: Record<string, number>
  total: number
}

// ── Board catalog entity (GET /api/hardware/boards[/{id}]) ─────────────────────
export interface BoardSummary {
  board_id: string
  manufacturer?: string
  model?: string
  display_name?: string
  boardClass?: string
  portsSummary?: Record<string, number>
  portCount?: number
  linkStatus?: string
}

export interface BoardsResult {
  total: number
  count: number
  offset: number
  limit: number
  boards: BoardSummary[]
}

export interface BoardPinDetail {
  pin: string
  signal?: string
  configKey?: string
  invert?: boolean
  pullup?: boolean
  hint?: string
}

export interface BoardPort {
  label?: string
  category?: string
  portFunction?: string
  connectorStyle?: string
  pins?: string | number
  pitchMm?: string | number
  notes?: string
  hint?: string
  configKey?: string
  configSection?: string
  pinMap?: BoardPinDetail[]
}

export interface BoardMedia {
  productUrl?: string
  repoUrl?: string
  wikiUrl?: string
  imageUrl?: string
  pinoutUrl?: string
  schematicUrl?: string
  datasheetUrl?: string
  mediaStatus?: string
}

export interface BoardDetail extends BoardSummary {
  specs?: Record<string, string>
  ports?: BoardPort[]
  media?: BoardMedia
  electronics?: Record<string, string>
  configNotes?: string[]
  configSnippet?: string
}

// ── Driver catalog entity (GET /api/hardware/drivers[/{id}]) ───────────────────
export interface DriverSummary {
  driver_id: string
  name?: string
  manufacturer?: string
  chip?: string
  interface?: string
  klipperSupported?: boolean
  klipperSection?: string | null
  sensorless?: boolean
  specCount?: number
}

export interface DriversResult {
  total: number
  count: number
  offset: number
  limit: number
  drivers: DriverSummary[]
}

export interface DriverDetail extends DriverSummary {
  aliases?: string[]
  specs?: Record<string, string>
  configSnippet?: string
  configSource?: string
}

// ── Motor catalog entity (GET /api/hardware/motors[/{id}]) ─────────────────────
export interface MotorSummary {
  motor_id: string
  name?: string
  manufacturer?: string
  nema?: string
  stepAngle?: string
  ratedCurrent?: string
  holdingTorque?: string
  recommendedRunCurrent?: number | null
  presetCount?: number
}

export interface MotorsResult {
  total: number
  count: number
  offset: number
  limit: number
  motors: MotorSummary[]
}

export interface MotorCurrentPreset {
  driver?: string
  axis?: string
  run_current?: string
  voltage?: string
}

export interface MotorDetail extends MotorSummary {
  aliases?: string[]
  specs?: Record<string, string>
  currentPresets?: MotorCurrentPreset[]
  configSnippet?: string
  configSource?: string
}

// ── Host catalog entity (GET /api/hardware/hosts[/{id}]) ───────────────────────
export interface HostSummary {
  host_id: string
  name?: string
  manufacturer?: string
  kind?: string
  soc?: string
  ram?: string
  klipperOs?: string
  klipperOpen?: boolean
  specCount?: number
}

export interface HostsResult {
  total: number
  count: number
  offset: number
  limit: number
  hosts: HostSummary[]
}

export interface HostDetail extends HostSummary {
  cpu?: string
  specs?: Record<string, string>
  configSnippet?: string
  configSource?: string
}

// ── Generic catalog entity (GET /api/hardware/catalog?category=…[ /{id}]) ──────
export interface CatalogSummary {
  catalog_id: string
  name?: string
  manufacturer?: string
  category?: string
  subsection?: string
  specCount?: number
}

export interface CatalogResult {
  total: number
  count: number
  offset: number
  limit: number
  entities: CatalogSummary[]
}

export interface CatalogEntityDetail extends CatalogSummary {
  specs?: Record<string, string>
  configSnippet?: string
  configSource?: string
}
