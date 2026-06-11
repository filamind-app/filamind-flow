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
  /** Effective cruise speed (mm/s), commanded feedrate capped at the machine's max_velocity. */
  v_mm_s?: number
  /** Accel-aware time for this move (s). */
  time_s?: number
  /** Extrusion rate during the move (filament mm/s ≈ mm³/s), 0 for travel moves. */
  extrude_rate?: number
  extruding: boolean
  out_of_bounds?: boolean
  over_speed?: boolean
}

/** The printer's real build envelope + speed cap (from `/api/macro/limits`). */
export interface MachineLimits {
  min: [number, number, number]
  max: [number, number, number]
  max_velocity: number | null
  max_accel: number | null
}

export interface MachineLimitsResult {
  reachable: boolean
  limits: MachineLimits | null
}

/** A move that leaves the build area / exceeds the speed cap. */
export interface SimViolation {
  line: number
  kind: 'out_of_bounds' | 'over_speed' | string
  axis?: string
  value?: number
  limit?: number | number[]
}

/** A static macro-linter finding (rendered to a message + fix per rule). */
export interface LintFinding {
  level: 'error' | 'warn' | string
  line: number | null
  rule: string
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
  /** Which time model produced `est_time_s`: 'accel' (trapezoidal) or 'constant' (no limits). */
  time_model?: 'accel' | 'constant' | string
  move_count: number
  command_count: number
  warnings: string[]
  violations: SimViolation[]
  limits: MachineLimits | null
  lint: LintFinding[]
}

export interface MacroDef {
  id: string
  name: string
  title: string
  description: string
  required_sections: string[]
  expands_to: string[]
}

/** One of the printer's own installed `[gcode_macro]` definitions, from `/api/macro/live`. */
export interface LiveMacro {
  name: string
  gcode: string
  description: string
  params: Record<string, string>
  variables: Record<string, unknown>
}

export interface LiveMacrosResult {
  reachable: boolean
  macros: LiveMacro[]
}
