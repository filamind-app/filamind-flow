/** Pure display helpers for the Motor Drivers dashboard — kept out of the component
 *  so they're unit-testable and the template stays declarative.
 */
import { i18n } from '@/core/i18n'
import type { DriverRecommendation, MotorSpec, TmcDriver } from './types'

/** "tmc2209" -> "TMC2209". */
export function driverModelLabel(model: string): string {
  return model.toUpperCase()
}

/** Live current with the configured value appended when they differ (TMCs quantise
 *  the requested current to an achievable step, so live ≠ set is normal and worth showing). */
export function currentLabel(live: number | null, config: number | null): string {
  if (live != null) {
    const base = i18n.global.t('motorDrivers.format.amps', { a: live.toFixed(2) })
    if (config != null && Math.abs(config - live) >= 0.01)
      return i18n.global.t('motorDrivers.format.ampsSet', { base, set: config.toFixed(2) })
    return base
  }
  if (config != null) return i18n.global.t('motorDrivers.format.amps', { a: config.toFixed(2) })
  return '—'
}

/** Human chopper-mode description, including the StealthChop velocity threshold. */
export function chopperLabel(d: TmcDriver): string {
  if (d.chopper_mode === 'StealthChop') {
    const t = d.stealthchop_threshold
    return t != null && t > 0 && t < 99999
      ? i18n.global.t('motorDrivers.format.stealthchopThreshold', { t })
      : i18n.global.t('motorDrivers.format.stealthchop')
  }
  if (d.chopper_mode === 'SpreadCycle') return i18n.global.t('motorDrivers.format.spreadcycle')
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
  if (!s) return { tone: 'idle', label: i18n.global.t('motorDrivers.format.health.idle') }
  const flag = (k: string): boolean => Boolean(s[k])
  if (flag('ot') || flag('s2ga') || flag('s2gb') || flag('s2vsa') || flag('s2vsb')) {
    return { tone: 'error', label: i18n.global.t('motorDrivers.format.health.fault') }
  }
  if (flag('otpw') || flag('ola') || flag('olb'))
    return { tone: 'warn', label: i18n.global.t('motorDrivers.format.health.warning') }
  return { tone: 'ok', label: i18n.global.t('motorDrivers.format.health.ok') }
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
  if (d.temperature != null)
    return i18n.global.t('motorDrivers.format.celsius', { v: d.temperature.toFixed(1) })
  return d.model === 'tmc2240' ? '—' : i18n.global.t('motorDrivers.format.noSensor')
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

/** The effective run-current ceiling: the server's `current_cap` (= min(model code cap, the
 *  assigned motor's rating)) when known, else the catalog's model cap. Preferring `current_cap`
 *  fixes the misleading "≤ 10.6 A" a TMC5160's *sanity ceiling* would otherwise show (#102) —
 *  once a motor is assigned, the real (motor-bound) limit is used. */
export function effectiveCap(d: TmcDriver): number | null {
  return d.current_cap ?? d.info?.max_current_a ?? null
}

/** Max current cap, e.g. "≤ 2.0 A", or '' if unknown. */
export function maxCurrentLabel(d: TmcDriver): string {
  const a = effectiveCap(d)
  return a != null ? i18n.global.t('motorDrivers.format.maxCurrent', { a: a.toFixed(1) }) : ''
}

/** Whether the run current is close to (or over) the effective cap — a gentle warning. */
export function nearCurrentCap(d: TmcDriver): boolean {
  const cap = effectiveCap(d)
  const run = d.run_current ?? d.run_current_config
  return cap != null && run != null && run >= cap * 0.9
}

/** "stepper_x" -> "X axis" / "extruder" -> "Extruder" — a friendly card heading. */
export function axisHeading(d: TmcDriver): string {
  if (d.axis && /^E\d*$/.test(d.axis))
    return d.axis === 'E'
      ? i18n.global.t('motorDrivers.format.extruder')
      : i18n.global.t('motorDrivers.format.extruderN', { n: d.axis.slice(1) })
  if (d.axis) return i18n.global.t('motorDrivers.format.axis', { axis: d.axis })
  return d.stepper
}

/** Human label for a homing-method classification (the backend `homing_method`). */
export function homingMethodLabel(method: string | null): string {
  switch (method) {
    case 'sensorless':
      return i18n.global.t('motorDrivers.format.homing.sensorless')
    case 'physical':
      return i18n.global.t('motorDrivers.format.homing.physical')
    case 'probe':
      return i18n.global.t('motorDrivers.format.homing.probe')
    case 'other_virtual':
      return i18n.global.t('motorDrivers.format.homing.otherVirtual')
    case 'inherited':
      return i18n.global.t('motorDrivers.format.homing.inherited')
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

/** The live trigger state for an axis from the `/api/drivers/endstops` map. Moonraker keys
 *  endstops by the rail/stepper name, which is `stepper_x` on some printers (the SV08) and the
 *  bare axis letter `x` on others — so try the stepper section name first, then the axis letter. */
export function endstopStateFor(
  states: Record<string, string>,
  stepper: string,
  axis: string | null,
): string | null {
  if (states[stepper] != null) return states[stepper]
  const key = axis?.toLowerCase()
  if (key && states[key] != null) return states[key]
  return null
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
      hint: i18n.global.t('motorDrivers.format.stallguard.signed'),
    }
  }
  return {
    min: 0,
    max: 255,
    hint: i18n.global.t('motorDrivers.format.stallguard.unsigned'),
  }
}

/** A motor's key datasheet specs as a compact line, e.g. "0.40 Nm · 1.7 A · 1.5 Ω · 2.8 mH". */
export function motorSpecLabel(m: MotorSpec): string {
  const parts: string[] = []
  if (m.holding_torque_Nm != null)
    parts.push(i18n.global.t('motorDrivers.format.spec.nm', { v: m.holding_torque_Nm.toFixed(2) }))
  if (m.max_current_A != null)
    parts.push(i18n.global.t('motorDrivers.format.spec.amps', { v: m.max_current_A.toFixed(1) }))
  if (m.resistance_ohm != null)
    parts.push(i18n.global.t('motorDrivers.format.spec.ohm', { v: m.resistance_ohm }))
  if (m.inductance_H != null)
    parts.push(
      i18n.global.t('motorDrivers.format.spec.mh', { v: (m.inductance_H * 1000).toFixed(1) }),
    )
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
    ['ot', i18n.global.t('motorDrivers.format.flag.overtemp')],
    ['otpw', i18n.global.t('motorDrivers.format.flag.tempWarn')],
    ['s2ga', i18n.global.t('motorDrivers.format.flag.shortA')],
    ['s2gb', i18n.global.t('motorDrivers.format.flag.shortB')],
    ['s2vsa', i18n.global.t('motorDrivers.format.flag.shortA')],
    ['s2vsb', i18n.global.t('motorDrivers.format.flag.shortB')],
    ['ola', i18n.global.t('motorDrivers.format.flag.openLoadA')],
    ['olb', i18n.global.t('motorDrivers.format.flag.openLoadB')],
    ['stst', i18n.global.t('motorDrivers.format.flag.standstill')],
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
    row(i18n.global.t('motorDrivers.format.runCurrent'), d.run_current, rec.run_current),
    row('pwm_grad', num(reg.pwm_grad), rec.pwm_grad),
    row('pwm_ofs', num(reg.pwm_ofs), rec.pwm_ofs),
    row('hstrt', num(reg.hstrt), rec.hstrt),
    row('hend', num(reg.hend), rec.hend),
  ]
}
