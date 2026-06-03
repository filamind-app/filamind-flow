/** Pure display helpers for the Motor Drivers dashboard — kept out of the component
 *  so they're unit-testable and the template stays declarative.
 */
import type { MotorSpec, TmcDriver } from './types'

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

/** Authoritative capabilities from the driver catalog when known, else the
 *  config-inferred set. The catalog is verified per-model, so prefer it. */
export function effectiveCapabilities(d: TmcDriver): Record<string, boolean> {
  const i = d.info
  if (!i) return d.capabilities
  return {
    stealthchop: !!i.stealthchop,
    spreadcycle: !!i.spreadcycle,
    coolstep: !!i.coolstep,
    stallguard: !!i.stallguard,
    temperature: !!i.temperature,
  }
}

/** Capabilities present, as short uppercase chips, in a stable order. */
export function capabilityChips(caps: Record<string, boolean>): string[] {
  const order = ['stealthchop', 'spreadcycle', 'coolstep', 'stallguard', 'temperature']
  return order.filter((k) => caps[k]).map((k) => k.toUpperCase())
}

/** Communication interface from the catalog (UART / SPI / UART·SPI), or '' if unknown. */
export function interfaceLabel(d: TmcDriver): string {
  return d.info?.interface?.replace('/', '·') ?? ''
}

/** Max current cap from the catalog, e.g. "≤ 2.0 A", or '' if unknown. */
export function maxCurrentLabel(d: TmcDriver): string {
  const a = d.info?.max_current_a
  return a != null ? `≤ ${a.toFixed(1)} A` : ''
}

/** Whether the run current is close to (or over) the model's rated cap — a gentle warning. */
export function nearCurrentCap(d: TmcDriver): boolean {
  const cap = d.info?.max_current_a
  const run = d.run_current ?? d.run_current_config
  return cap != null && run != null && run >= cap * 0.9
}

/** "stepper_x" -> "X axis" / "extruder" -> "Extruder" — a friendly card heading. */
export function axisHeading(d: TmcDriver): string {
  if (d.axis && /^E\d*$/.test(d.axis))
    return d.axis === 'E' ? 'Extruder' : `Extruder ${d.axis.slice(1)}`
  if (d.axis) return `${d.axis} axis`
  return d.stepper
}

/** A motor's key datasheet specs as a compact line, e.g. "0.40 Nm · 1.7 A · 1.5 Ω · 2.8 mH". */
export function motorSpecLabel(m: MotorSpec): string {
  const parts: string[] = []
  if (m.holding_torque_Nm != null) parts.push(`${m.holding_torque_Nm.toFixed(2)} Nm`)
  if (m.max_current_A != null) parts.push(`${m.max_current_A.toFixed(1)} A`)
  if (m.resistance_ohm != null) parts.push(`${m.resistance_ohm} Ω`)
  if (m.inductance_H != null) parts.push(`${(m.inductance_H * 1000).toFixed(1)} mH`)
  return parts.join(' · ') || '—'
}

/** Filters the motor catalog by a free-text query over model + manufacturer. */
export function filterMotors(catalog: MotorSpec[], query: string): MotorSpec[] {
  const q = query.trim().toLowerCase()
  if (!q) return catalog
  return catalog.filter(
    (m) => m.model.toLowerCase().includes(q) || m.manufacturer.toLowerCase().includes(q),
  )
}
