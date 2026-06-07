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
