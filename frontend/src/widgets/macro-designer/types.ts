/** Shapes for the Macro Designer (backed by `/api/macro/simulate` + `/api/reference/macros`). */

export interface PathPoint {
  x: number
  y: number
  extruding: boolean
}

export interface SimSegment {
  line: number
  from: [number, number, number]
  to: [number, number, number]
  e_delta: number
  dist: number
  feedrate: number
  extruding: boolean
}

export interface TimelineEntry {
  line: number
  cmd: string
  action: string
}

export interface SimBounds {
  min_x: number
  max_x: number
  min_y: number
  max_y: number
  min_z: number
  max_z: number
}

export interface SimResult {
  segments: SimSegment[]
  path2d: PathPoint[]
  timeline: TimelineEntry[]
  bounds: SimBounds
  total_distance_mm: number
  total_extrude_mm: number
  est_time_s: number
  move_count: number
  command_count: number
  warnings: string[]
}

export interface MacroDef {
  id: string
  name: string
  title: string
  description: string
  required_sections: string[]
  expands_to: string[]
}
