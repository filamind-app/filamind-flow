/** Shapes for the Max-Flow widget (backed by `/api/maxflow/*` and `/api/reference/hotends`). */

export interface HotendRow {
  name: string
  melt_zone_mm?: number
  expected_max_flow_mm3s?: number
  suggested_temp_c?: number
  [key: string]: unknown
}

export interface MaxFlowParams {
  temperature: number
  start_flow: number
  end_flow: number
  step_flow: number
  filament_diameter: number
  extrude_per_step: number
  samples_per_step: number
  driver: string
  /** Home (if needed) + center the nozzle for a clear view before heating. */
  park_for_view?: boolean
}

export interface PlanStep {
  flow_mm3s: number
  feedrate_mm_min: number
  extrude_mm: number
}

export interface MaxFlowPlan {
  driver: string
  stallguard_field: string | null
  temperature: number
  filament_diameter: number
  samples_per_step: number
  step_count: number
  total_extrude_mm: number
  steps: PlanStep[]
}

export interface ResultStep {
  flow: number
  median: number
  iqr: number
  cv_pct: number
  n: number
}

export interface MaxFlowRecommendation {
  max: number | null
  conservative: number | null
  balanced: number | null
}

export interface MaxFlowResult {
  ok: boolean
  max_flow_mm3s: number | null
  slip_flow: number | null
  reason: string
  steps: ResultStep[]
  recommend: MaxFlowRecommendation
  driver: string
  stallguard_field: string | null
  sg_samples_seen: boolean
}
