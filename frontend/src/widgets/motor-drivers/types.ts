/** Mirrors the backend `DriversStatus` / `TmcDriver` schema (GET /api/drivers/status). */

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
}

export interface DriversStatus {
  reachable: boolean
  drivers: TmcDriver[]
}
