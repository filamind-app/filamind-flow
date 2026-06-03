/** Pure display helpers for the Motor Drivers dashboard — kept out of the component
 *  so they're unit-testable and the template stays declarative.
 */
import type { TmcDriver } from './types'

/** "tmc2209" -> "TMC2209". */
export function driverModelLabel(model: string): string {
  return model.toUpperCase()
}

/** Live current with the configured value appended when they differ (TMCs quantise
 *  the requested current to an achievable step, so live ≠ set is normal and worth showing). */
export function currentLabel(live: number | null, config: number | null): string {
  if (live != null) {
    const base = `${live.toFixed(2)} A`
    if (config != null && Math.abs(config - live) >= 0.01)
      return `${base} (set ${config.toFixed(2)})`
    return base
  }
  if (config != null) return `${config.toFixed(2)} A`
  return '—'
}

/** Human chopper-mode description, including the StealthChop velocity threshold. */
export function chopperLabel(d: TmcDriver): string {
  if (d.chopper_mode === 'StealthChop') {
    const t = d.stealthchop_threshold
    return t != null && t > 0 && t < 99999 ? `StealthChop < ${t} mm/s` : 'StealthChop'
  }
  if (d.chopper_mode === 'SpreadCycle') return 'SpreadCycle'
  return d.chopper_mode ?? '—'
}

export type DriverHealthTone = 'idle' | 'ok' | 'warn' | 'error'
export interface DriverHealth {
  tone: DriverHealthTone
  label: string
}

/** Live health from the drv_status fault flags. When the motor is disabled Klipper
 *  reports no drv_status, so we show "idle" rather than a false "ok". */
export function driverHealth(d: TmcDriver): DriverHealth {
  const s = d.drv_status
  if (!s) return { tone: 'idle', label: 'idle' }
  const flag = (k: string): boolean => Boolean(s[k])
  if (flag('ot') || flag('s2ga') || flag('s2gb') || flag('s2vsa') || flag('s2vsb')) {
    return { tone: 'error', label: 'fault' }
  }
  if (flag('otpw') || flag('ola') || flag('olb')) return { tone: 'warn', label: 'warning' }
  return { tone: 'ok', label: 'ok' }
}

/** Tailwind classes for a health badge by tone. */
export function healthClass(tone: DriverHealthTone): string {
  if (tone === 'ok') return 'bg-brand-lime'
  if (tone === 'warn') return 'bg-brand-yellow'
  if (tone === 'error') return 'bg-brand-red text-surface'
  return 'bg-surface opacity-60'
}

/** Temperature string, or a clear note for models without a sensor (only the 2240 has one). */
export function temperatureLabel(d: TmcDriver): string {
  if (d.temperature != null) return `${d.temperature.toFixed(1)} °C`
  return d.model === 'tmc2240' ? '—' : 'no sensor'
}

/** Capabilities present, as short uppercase chips, in a stable order. */
export function capabilityChips(caps: Record<string, boolean>): string[] {
  const order = ['stealthchop', 'spreadcycle', 'coolstep', 'stallguard', 'temperature']
  return order.filter((k) => caps[k]).map((k) => k.toUpperCase())
}

/** "stepper_x" -> "X axis" / "extruder" -> "Extruder" — a friendly card heading. */
export function axisHeading(d: TmcDriver): string {
  if (d.axis && /^E\d*$/.test(d.axis))
    return d.axis === 'E' ? 'Extruder' : `Extruder ${d.axis.slice(1)}`
  if (d.axis) return `${d.axis} axis`
  return d.stepper
}
