/** One (Z height -> PA) point on the tuning tower (mirrors the backend PaSample). */
export interface PaSample {
  height: number
  pa: number
}

export interface PaTowerParams {
  start: number
  factor: number
  height: number
}

export interface PaTowerPlan {
  command: string
  start: number
  factor: number
  height: number
  samples: PaSample[]
}

export interface PaApplyResult {
  ok: boolean
  code: 'applied' | 'busy' | 'out_of_range' | 'moonraker_error' | string
  params: Record<string, unknown>
}

export function defaultParams(): PaTowerParams {
  return { start: 0, factor: 0.005, height: 50 }
}
