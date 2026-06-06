/** Shapes returned by `GET /api/topology`. */

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
}

/** A port on a catalog board (subset used by the topology board card). */
export interface BoardPort {
  label?: string
  category?: string
  portFunction?: string
  connectorStyle?: string
  pins?: string | number
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
