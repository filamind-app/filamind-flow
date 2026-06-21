/** One (Z height -> value) point on a tuning tower. The value key differs per wizard:
 *  Pressure Advance uses `pa`, retraction uses `value`. */
export interface PaSample {
  height: number
  pa: number
}

export interface RetractionSample {
  height: number
  value: number
}

export interface TowerParams {
  start: number
  factor: number
  height: number
}

/** Backwards-compatible alias (PA params share the generic tower shape). */
export type PaTowerParams = TowerParams

export interface PaTowerPlan {
  command: string
  start: number
  factor: number
  height: number
  samples: PaSample[]
}

export interface RetractionTowerPlan {
  command: string
  start: number
  factor: number
  height: number
  samples: RetractionSample[]
}

/** A tower plan as the generic wizard consumes it (samples keyed dynamically by `valueKey`). */
export interface TowerPlan {
  command: string
  start: number
  factor: number
  height: number
  samples: Array<Record<string, number>>
}

export interface ApplyResult {
  ok: boolean
  code: string
  params: Record<string, unknown>
}

/** Backwards-compatible alias. */
export type PaApplyResult = ApplyResult

export function defaultParams(): TowerParams {
  return { start: 0, factor: 0.005, height: 50 }
}

export function defaultRetractionParams(): TowerParams {
  return { start: 0, factor: 0.05, height: 50 }
}

/** Temperature tower (BAND mode) - one constant-temperature band (Z range -> temperature). */
export interface TempBand {
  z_low: number
  z_high: number
  temp: number
}

export interface TempTowerParams {
  start: number
  factor: number
  band: number
  height: number
  heater: string
}

export interface TempTowerPlan {
  command: string
  start: number
  factor: number
  band: number
  height: number
  heater: string
  bands: TempBand[]
}

export function defaultTempParams(): TempTowerParams {
  return { start: 240, factor: -0.5, band: 10, height: 100, heater: 'extruder' }
}

/** Heaters a temperature tower may target (mirrors the backend allowlist). */
export const HEATERS = ['extruder', 'extruder1', 'extruder2', 'heater_bed'] as const
