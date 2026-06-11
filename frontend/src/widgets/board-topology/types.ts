/** Shapes returned by `GET /api/topology`. */

import type { RelatedRef } from '@/widgets/hardware-browser/types'

export type { RelatedRef }

/** A component (stepper / driver / heater / fan / sensor) attached to an MCU. */
export interface TopologyComponent {
  section: string
  kind: 'motor' | 'driver' | 'heater' | 'fan' | 'sensor'
}

export interface TopologyMcu {
  name: string
  connection: 'canbus' | 'usb' | 'uart' | 'unknown'
  identifier: string | null
  mcu: string | null
  /** Canonical DB MCU entity id (one of the first-class MCUs); null if unrecognised. */
  mcu_id?: string | null
  mcu_family?: string | null
  board: string | null
  confidence: number
  /** Link into the board catalog; null when only the chip could be identified. */
  board_id?: string | null
  /** `suggested` = auto-detected guess; `confirmed` = the user confirmed / overrode it. */
  board_match?: 'suggested' | 'confirmed' | null
  board_match_confidence?: number
  /** The components (steppers / drivers / heaters / fans / sensors) that live on this MCU. */
  components?: TopologyComponent[]
}

/** A port on a catalog board (subset used by the topology board card). */
export interface BoardPort {
  label?: string
  category?: string
  portFunction?: string
  connectorStyle?: string
  pins?: string | number
}

/** Per-board media / reference links (all optional, link-only). */
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

/** Full board record from `GET /api/hardware/boards/{board_id}`. */
export interface BoardDetail {
  board_id: string
  manufacturer?: string
  model?: string
  display_name?: string
  boardClass?: string
  specs?: Record<string, string>
  /** Config-affecting electronics caveats (key → note). */
  electronics?: Record<string, string>
  /** Setup / config notes for this board. */
  configNotes?: string[]
  /** Copyable verbatim Klipper config / pin-map block. */
  configSnippet?: string
  configSource?: string
  ports?: BoardPort[]
  portsSummary?: Record<string, number>
  media?: BoardMedia
  /** Cross-entity links (manufacturer / mcus / onboardDrivers / supportedDrivers / …), inlined
   *  by `?expand=related`. Keyed by relation → the neighbour refs. */
  related?: Record<string, RelatedRef[]>
  relatedCounts?: Record<string, number>
}

export interface TopologyHost {
  name: string
  role: string
  /** Best-effort link to a catalog host entity (one of the DB hosts); null if unmatched. */
  host_id?: string | null
  host_match?: 'suggested' | null
  host_match_confidence?: number
  /** Set to a mainboard id when the host SBC is physically integrated on that board (SV08 / Manta
   *  + CB1) — lets the map draw the host inside the board. */
  integrated_into_board_id?: string | null
}

export interface Topology {
  reachable?: boolean
  host: TopologyHost | null
  mcus: TopologyMcu[]
  mcu_count: number
  detail?: string
}

/** One named pin of a board, from `GET /api/topology/pin-atlas/{mcu_name}`. */
export interface PinAtlasPin {
  pin: string
  signal?: string | null
  config_key?: string | null
  hint?: string | null
  category?: string | null
  port?: string | null
  used: boolean
  owners: string[]
  caveat?: string | null
}

export interface PinFinding {
  kind: 'double_assign' | 'caveat' | string
  pin: string
  message: string
  sections: string[]
}

export interface PinAtlas {
  mcu_name: string
  board_id?: string | null
  board_name?: string | null
  available: boolean
  total: number
  used: number
  free: number
  pins: PinAtlasPin[]
  findings: PinFinding[]
}

/** One change between the saved hardware baseline and the live topology. */
export interface TopologyChange {
  mcu: string
  kind:
    | 'added'
    | 'removed'
    | 'board_changed'
    | 'connection_changed'
    | 'chip_changed'
    | 'components_changed'
    | string
  before?: string | null
  after?: string | null
}

export interface TopologyDiff {
  has_baseline: boolean
  saved_at?: string | null
  changes: TopologyChange[]
}
