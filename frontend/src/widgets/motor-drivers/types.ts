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
}

export interface DriversStatus {
  reachable: boolean
  drivers: TmcDriver[]
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
