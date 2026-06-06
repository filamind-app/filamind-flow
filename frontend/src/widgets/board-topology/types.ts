/** Shapes returned by `GET /api/topology`. */

export interface TopologyMcu {
  name: string
  connection: 'canbus' | 'usb' | 'uart' | 'unknown'
  identifier: string | null
  mcu: string | null
  board: string | null
  confidence: number
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
