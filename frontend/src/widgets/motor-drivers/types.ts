/** Mirrors the backend `DriversStatus` / `TmcDriver` / `DriverCatalog` schemas
 *  (GET /api/drivers/status, GET /api/drivers/catalog). */

/** Reference capabilities for a TMC model, from the curated driver catalog. */
export interface DriverInfo {
  model: string
  name: string
  interface: string | null
  max_current_a: number | null
  current_note: string | null
  microsteps: number | null
  stealthchop: boolean | null
  spreadcycle: boolean | null
  coolstep: boolean | null
  stallguard: boolean | null
  stallguard_field: string | null
  sensorless: boolean | null
  temperature: boolean | null
  aliases: string[]
  notes: string | null
}

/** A stepper motor's datasheet parameters, from the motor catalog. */
export interface MotorSpec {
  manufacturer: string
  model: string
  resistance_ohm: number | null
  inductance_H: number | null
  holding_torque_Nm: number | null
  max_current_A: number | null
  steps_per_rev: number
  source: string
}

export interface TmcDriver {
  stepper: string
  model: string
  axis: string | null
  run_current: number | null
  hold_current: number | null
  run_current_config: number | null
  hold_current_config: number | null
  sense_resistor: number | null
  /** TMC2240 external reference resistor (Ω); its current cap is derived from this. */
  rref: number | null
  microsteps: number | null
  interpolate: boolean | null
  stealthchop_threshold: number | null
  chopper_mode: string | null
  stallguard_field: string | null
  stallguard_threshold: number | null
  temperature: number | null
  drv_status: Record<string, unknown> | null
  capabilities: Record<string, boolean>
  registers: Record<string, unknown>
  info: DriverInfo | null
  motor: MotorSpec | null
  /** Effective run-current ceiling (A): min(model code cap, assigned motor's rating), or null. */
  current_cap: number | null
  /** How this axis homes, classified from `[stepper_*].endstop_pin` (P9):
   *  'sensorless' | 'physical' | 'probe' | 'other_virtual' | 'inherited'. */
  homing_method: string | null
  endstop_pin: string | null
  homing_note: string | null
}

/** Live endstop trigger state (GET /api/drivers/endstops). */
export interface EndstopStates {
  reachable: boolean
  states: Record<string, string>
}

export interface DriversStatus {
  reachable: boolean
  drivers: TmcDriver[]
}

/** Mirrors the backend `DriverLive` (GET /api/drivers/live/{stepper}). */
export interface DriverLive {
  reachable: boolean
  stepper: string
  model: string | null
  temperature: number | null
  run_current: number | null
  drv_status: Record<string, unknown> | null
}

export interface DriverCatalog {
  source: string
  drivers: DriverInfo[]
}

export interface MotorCatalog {
  source: string
  count: number
  manufacturers: string[]
  motors: MotorSpec[]
}

/** Mirrors the backend `DriverRecommendation` (POST /api/drivers/recommend). */
export interface DriverRecommendation {
  motor_model: string
  motor_name: string
  run_current: number
  run_current_basis: string
  pwm_grad: number
  pwm_ofs: number
  hstrt: number
  hend: number
  max_pwm_rps: number
  cbemf: number
  voltage: number
  toff: number
  tbl: number
}

export interface RecommendRequest {
  motor_model: string
  voltage?: number
  run_current?: number | null
  is_2240?: boolean
}

export interface ApplyRequest {
  stepper: string
  run_current?: number | null
  hold_current?: number | null
  fields?: Record<string, number>
}

export interface ConfigBlockRequest {
  stepper: string
  model: string
  run_current?: number | null
  fields?: Record<string, number>
}

/** Result of a write / revert / autotune: whether it ran + the exact g-code sent. */
export interface ApplyResponse {
  ok: boolean
  applied: string[]
  message: string
}

/** Whether the motors_sync add-on is installed (GET /api/drivers/motors-sync). */
export interface MotorsSyncStatus {
  available: boolean
}
