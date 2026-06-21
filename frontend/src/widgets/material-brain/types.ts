/** A saved filament profile (mirrors the backend MaterialProfile schema). */
export interface MaterialProfile {
  id: string
  name: string
  material: string
  brand: string
  color: string
  diameter: number
  density: number
  nozzle_temp: number
  bed_temp: number
  max_volumetric_flow: number
  notes: string
}

/** Verdict of a profile's max volumetric flow vs the hotend's catalog ceiling. */
export interface MaterialFlowCheck {
  code: 'unset' | 'no_ceiling' | 'exceeds' | 'within' | string
  level: 'ok' | 'warn' | string
  params: Record<string, unknown>
}

/** A blank profile for the "add" form. */
export function emptyProfile(): MaterialProfile {
  return {
    id: '',
    name: '',
    material: 'PLA',
    brand: '',
    color: '',
    diameter: 1.75,
    density: 1.24,
    nozzle_temp: 210,
    bed_temp: 60,
    max_volumetric_flow: 0,
    notes: '',
  }
}
