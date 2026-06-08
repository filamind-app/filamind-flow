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
  board: string | null
  confidence: number
  /** Link into the board catalog; null when only the chip could be identified. */
  board_id?: string | null
  board_match?: 'suggested' | null
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
}

export interface Topology {
  reachable?: boolean
  host: TopologyHost | null
  mcus: TopologyMcu[]
  mcu_count: number
  detail?: string
}
