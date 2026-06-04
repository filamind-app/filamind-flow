/** Pure display helpers for the Motor Drivers dashboard — kept out of the component
 *  so they're unit-testable and the template stays declarative.
 */
import type { DriverRecommendation, MotorSpec, TmcDriver } from './types'

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

/** Human label for a homing-method classification (the backend `homing_method`). */
export function homingMethodLabel(method: string | null): string {
  switch (method) {
    case 'sensorless':
      return 'Sensorless (StallGuard)'
    case 'physical':
      return 'Physical endstop'
    case 'probe':
      return 'Z probe'
    case 'other_virtual':
      return 'Virtual endstop'
    case 'inherited':
      return 'Shared rail'
    default:
      return '—'
  }
}

/** Whether a homing panel applies to this axis. Extra motors on a shared rail (a second Z,
 *  the extruder) don't home on their own, so they get no homing UI. */
export function homingApplies(method: string | null): boolean {
  return (
    method === 'sensorless' ||
    method === 'physical' ||
    method === 'probe' ||
    method === 'other_virtual'
  )
}

/** Input range + polarity hint for a StallGuard threshold register — which differs by model,
 *  and getting it wrong makes the control feel backwards. `sgthrs` (2209) and `sg4_thrs` (2240)
 *  are unsigned 0–255 where HIGHER is more sensitive; `sgt` (2130 / 5160 / 2660) is a signed
 *  −64…63 where LOWER is more sensitive. */
export function stallguardRange(field: string | null): { min: number; max: number; hint: string } {
  if (field === 'sgt') {
    return {
      min: -64,
      max: 63,
      hint: 'Signed −64…63 — LOWER is more sensitive (stops sooner). Raise it if the axis stops short; lower it if it never stops.',
    }
  }
  return {
    min: 0,
    max: 255,
    hint: 'Range 0–255 — HIGHER is more sensitive (stops sooner). Lower it if the axis stops short; raise it if it never stops.',
  }
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

/** A numeric field from a live drv_status map (e.g. sg_result, cs_actual), or null. */
export function drvNum(drv: Record<string, unknown> | null, key: string): number | null {
  const v = drv?.[key]
  return typeof v === 'number' ? v : null
}

/** Live driver fault/status flags that are set, as short human labels (deduped). */
export function activeFlags(drv: Record<string, unknown> | null): string[] {
  if (!drv) return []
  const map: [string, string][] = [
    ['ot', 'overtemp'],
    ['otpw', 'temp-warn'],
    ['s2ga', 'short A'],
    ['s2gb', 'short B'],
    ['s2vsa', 'short A'],
    ['s2vsb', 'short B'],
    ['ola', 'open-load A'],
    ['olb', 'open-load B'],
    ['stst', 'standstill'],
  ]
  const out: string[] = []
  for (const [key, label] of map) {
    if (drv[key] && !out.includes(label)) out.push(label)
  }
  return out
}

/** An auto-scaled SVG path ("M…L…") for a sparkline of recent values. '' if too few points. */
export function sparklinePath(values: number[], width: number, height: number): string {
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = width / (values.length - 1)
  return values
    .map((v, i) => {
      const x = (i * step).toFixed(1)
      const y = (height - ((v - min) / span) * height).toFixed(1)
      return `${i === 0 ? 'M' : 'L'}${x},${y}`
    })
    .join(' ')
}

/** One row of the recommendation preview: the live value vs the recommended one. */
export interface RecRow {
  label: string
  current: number | null
  recommended: number
  changed: boolean
}

/** Builds the recommended-vs-current diff rows for a driver. `changed` is true when the
 *  live value is unknown or differs from the recommendation. */
export function recommendationRows(d: TmcDriver, rec: DriverRecommendation): RecRow[] {
  const reg = d.registers
  const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)
  const row = (label: string, current: number | null, recommended: number): RecRow => ({
    label,
    current,
    recommended,
    changed: current === null || current !== recommended,
  })
  return [
    row('run current (A)', d.run_current, rec.run_current),
    row('pwm_grad', num(reg.pwm_grad), rec.pwm_grad),
    row('pwm_ofs', num(reg.pwm_ofs), rec.pwm_ofs),
    row('hstrt', num(reg.hstrt), rec.hstrt),
    row('hend', num(reg.hend), rec.hend),
  ]
}
