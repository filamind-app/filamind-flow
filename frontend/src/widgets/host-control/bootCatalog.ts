/** The curated Boot-parameters catalog: the common, printer-relevant boot toggles for each host
 *  platform, plus the logic to READ an item's current value from the parsed boot file and to EMIT
 *  the typed ops for a new value. The panel renders this; the raw Advanced editor bypasses it.
 *
 *  Labels/purpose/caveat resolve through i18n at `hostControl.boot.params.items.<key>.*`, so this
 *  file carries only structure + mechanism, never English copy. */
import type { BootControl, BootFile, BootOp, BootPlatform } from './types'

/** One curated capability. The optional fields are per-`kind`; see readValue / opsForValue. */
export interface BootItem {
  key: string
  group: string
  control: BootControl
  kind:
    | 'overlay_toggle'
    | 'overlay_select'
    | 'armbian_key'
    | 'armbian_extraarg'
    | 'dtparam_toggle'
    | 'kv_toggle'
    | 'kv_number'
    | 'dtoverlay_toggle'
    | 'dtoverlay_select'
  file: 'armbianEnv.txt' | 'config.txt' | 'cmdline.txt'
  token?: string // overlay / dtoverlay name (toggle + select)
  variants?: string[] // option tokens for a select
  argKey?: string // armbian key / extraarg key / dtparam / kv key
  onValue?: string // value written when a toggle turns ON (armbian_key / dtparam / kv)
  offValue?: string // value written when a toggle turns OFF (armbian_key); unset ⇒ remove
  options?: string[] // select option values (armbian_key select, e.g. console)
  min?: number
  max?: number
  paramTemplate?: string // dtoverlay_select params, with `{v}` replaced by the chosen variant
  extraOn?: BootOp[] // extra ops prepended when enabling (e.g. rpi CAN needs spi=on)
}

export interface BootGroup {
  id: string
  items: BootItem[]
}

const ARMBIAN: BootGroup[] = [
  {
    id: 'hardware_interfaces',
    items: [
      {
        key: 'can_mcp2515',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'overlay_toggle',
        file: 'armbianEnv.txt',
        token: 'mcp2515',
      },
      {
        key: 'spi_accel',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'overlay_select',
        file: 'armbianEnv.txt',
        variants: ['spidev1_0', 'spidev1_1', 'spidev1_2', 'spidev3_0_m1'],
      },
      {
        key: 'i2c_bus',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'overlay_select',
        file: 'armbianEnv.txt',
        variants: ['i2c1', 'i2c3_m0', 'i2c4_m0'],
      },
      {
        key: 'uart_extra',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'overlay_select',
        file: 'armbianEnv.txt',
        variants: ['uart0', 'uart3_m0', 'uart5_m1', 'uart7_m2', 'uart9_m1'],
      },
      {
        key: 'ws2812',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'overlay_toggle',
        file: 'armbianEnv.txt',
        token: 'ws2812',
      },
      {
        key: 'rtc_module',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'overlay_select',
        file: 'armbianEnv.txt',
        variants: ['rtc_pcf8563', 'rtc_rk808'],
      },
    ],
  },
  {
    id: 'display_console',
    items: [
      {
        key: 'console_target',
        group: 'display_console',
        control: 'select',
        kind: 'armbian_key',
        file: 'armbianEnv.txt',
        argKey: 'console',
        options: ['display', 'serial', 'both'],
      },
      {
        key: 'bootlogo',
        group: 'display_console',
        control: 'toggle',
        kind: 'armbian_key',
        file: 'armbianEnv.txt',
        argKey: 'bootlogo',
        onValue: 'true',
        offValue: 'false',
      },
    ],
  },
  {
    id: 'performance_memory',
    items: [
      {
        key: 'cma_size',
        group: 'performance_memory',
        control: 'select',
        kind: 'armbian_extraarg',
        file: 'armbianEnv.txt',
        argKey: 'cma',
        variants: ['128M', '256M', '512M'],
      },
      {
        key: 'boot_verbosity',
        group: 'performance_memory',
        control: 'number',
        kind: 'armbian_key',
        file: 'armbianEnv.txt',
        argKey: 'verbosity',
        min: 0,
        max: 8,
      },
    ],
  },
]

const RPI: BootGroup[] = [
  {
    id: 'hardware_interfaces',
    items: [
      {
        key: 'enable_uart',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'kv_toggle',
        file: 'config.txt',
        argKey: 'enable_uart',
        onValue: '1',
      },
      {
        key: 'disable_bt',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'dtoverlay_toggle',
        file: 'config.txt',
        token: 'disable-bt',
      },
      {
        key: 'spi',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'dtparam_toggle',
        file: 'config.txt',
        argKey: 'spi',
        onValue: 'on',
      },
      {
        key: 'i2c_arm',
        group: 'hardware_interfaces',
        control: 'toggle',
        kind: 'dtparam_toggle',
        file: 'config.txt',
        argKey: 'i2c_arm',
        onValue: 'on',
      },
      {
        key: 'can_mcp2515',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'dtoverlay_select',
        file: 'config.txt',
        token: 'mcp2515-can0',
        variants: ['8000000', '12000000', '16000000', '20000000'],
        paramTemplate: 'oscillator={v},interrupt=25',
        extraOn: [{ op: 'set_dtparam', key: 'spi', value: 'on' }],
      },
      {
        key: 'i2c_rtc',
        group: 'hardware_interfaces',
        control: 'select',
        kind: 'dtoverlay_select',
        file: 'config.txt',
        token: 'i2c-rtc',
        variants: ['ds3231', 'ds1307', 'pcf8523', 'pcf8563'],
        paramTemplate: '{v}',
      },
    ],
  },
  {
    id: 'performance_memory',
    items: [
      {
        key: 'gpu_mem',
        group: 'performance_memory',
        control: 'number',
        kind: 'kv_number',
        file: 'config.txt',
        argKey: 'gpu_mem',
        min: 16,
        max: 256,
      },
      {
        key: 'arm_freq',
        group: 'performance_memory',
        control: 'number',
        kind: 'kv_number',
        file: 'config.txt',
        argKey: 'arm_freq',
        min: 600,
        max: 3000,
      },
      {
        key: 'over_voltage',
        group: 'performance_memory',
        control: 'number',
        kind: 'kv_number',
        file: 'config.txt',
        argKey: 'over_voltage',
        min: 0,
        max: 8,
      },
    ],
  },
  {
    id: 'usb_power',
    items: [
      {
        key: 'max_usb_current',
        group: 'usb_power',
        control: 'toggle',
        kind: 'kv_toggle',
        file: 'config.txt',
        argKey: 'max_usb_current',
        onValue: '1',
      },
    ],
  },
]

export const BOOT_CATALOG: Record<BootPlatform, BootGroup[]> = {
  armbian: ARMBIAN,
  rpi: RPI,
  unknown: [],
}

/** The parsed file an item edits (armbian has one; rpi splits config.txt / cmdline.txt). */
export function fileFor(files: BootFile[], item: BootItem): BootFile | undefined {
  return files.find((f) => f.name === item.file)
}

interface Scoped {
  section?: string | null
}
/** config.txt scopes a curated card reflects: the pre-filter global block and [all] (both apply to
 *  every model). A model-specific [pi4]/[cm4] line is not the current value the card edits. */
function editableScope(s?: string | null): boolean {
  return s == null || s === 'all'
}
/** The LAST editable-scope record matching a predicate - the assignment that actually wins. */
function lastEditable<T extends Scoped>(
  rows: T[] | undefined,
  pred: (r: T) => boolean,
): T | undefined {
  const m = (rows || []).filter((r) => editableScope(r.section) && pred(r))
  return m.length ? m[m.length - 1] : undefined
}
/** A dtparam/kv value read as on/off: a bare/absent value or a truthy token is on; off/0/false/no. */
function isTruthyValue(v: string | null | undefined): boolean {
  if (v == null || v === '') return true
  return !['off', 'false', '0', 'no'].includes(v.toLowerCase())
}
/** Whether a dtoverlay's params carry the given variant token (exact token or `<param>=<variant>`). */
function paramsHaveVariant(params: string, variant: string): boolean {
  return params.split(',').some((tok) => tok === variant || tok.split('=').pop() === variant)
}

/** The item's current value read from the parsed file: 'on'/'off' for toggles, the selected token
 *  (or '' when none) for selects, the raw value for keys/numbers. */
export function readValue(file: BootFile | undefined, item: BootItem): string {
  if (!file) return item.control === 'toggle' ? 'off' : ''
  switch (item.kind) {
    case 'overlay_toggle':
      return ((file.overlays as string[]) || []).includes(item.token ?? '') ? 'on' : 'off'
    case 'overlay_select': {
      const ov = (file.overlays as string[]) || []
      return item.variants?.find((v) => ov.includes(v)) ?? ''
    }
    case 'armbian_key': {
      const kv = (file.keys || []).find((k) => k.key === item.argKey)
      const val = kv ? kv.value : ''
      if (item.control === 'toggle') return val === item.onValue ? 'on' : 'off'
      return val
    }
    case 'armbian_extraarg': {
      const tok = (file.extraargs || []).find((t) => t.split('=', 1)[0] === item.argKey)
      return tok && tok.includes('=') ? tok.slice(tok.indexOf('=') + 1) : ''
    }
    case 'dtparam_toggle': {
      const d = lastEditable(file.dtparams, (r) => r.key === item.argKey)
      return d ? (isTruthyValue(d.value) ? 'on' : 'off') : 'off'
    }
    case 'kv_toggle': {
      const k = lastEditable(file.kv, (r) => r.key === item.argKey)
      return k ? (isTruthyValue(k.value) ? 'on' : 'off') : 'off'
    }
    case 'kv_number': {
      const k = lastEditable(file.kv, (r) => r.key === item.argKey)
      return k ? k.value : ''
    }
    case 'dtoverlay_toggle': {
      const ov = (file.overlays as { name: string; section?: string | null }[]) || []
      return lastEditable(ov, (o) => o.name === item.token) ? 'on' : 'off'
    }
    case 'dtoverlay_select': {
      const ov =
        (file.overlays as { name: string; params: string; section?: string | null }[]) || []
      const found = lastEditable(ov, (o) => o.name === item.token)
      if (!found) return ''
      // Return the matching catalog variant, or '' (unknown) - never a phantom variants[0].
      return item.variants?.find((v) => paramsHaveVariant(found.params, v)) ?? ''
    }
    default:
      return ''
  }
}

/** The typed ops to move an item from `cur` to `next` (empty when unchanged). */
export function opsForValue(item: BootItem, cur: string, next: string): BootOp[] {
  if (cur === next) return []
  switch (item.kind) {
    case 'overlay_toggle':
      return [{ op: next === 'on' ? 'add_overlay' : 'remove_overlay', name: item.token }]
    case 'overlay_select': {
      const ops: BootOp[] = []
      if (cur) ops.push({ op: 'remove_overlay', name: cur })
      if (next) ops.push({ op: 'add_overlay', name: next })
      return ops
    }
    case 'armbian_key': {
      const value =
        item.control === 'toggle' ? (next === 'on' ? item.onValue : item.offValue) : next
      if (item.control !== 'toggle' && value === '')
        return [{ op: 'set_key', key: item.argKey, value: '' }]
      return [{ op: 'set_key', key: item.argKey, value }]
    }
    case 'armbian_extraarg':
      return next
        ? [{ op: 'set_extraarg', key: item.argKey, value: next }]
        : [{ op: 'remove_extraarg', key: item.argKey }]
    case 'dtparam_toggle':
      return next === 'on'
        ? [{ op: 'set_dtparam', key: item.argKey, value: item.onValue ?? 'on' }]
        : [{ op: 'remove_dtparam', key: item.argKey }]
    case 'kv_toggle':
      return next === 'on'
        ? [{ op: 'set_kv', key: item.argKey, value: item.onValue ?? '1' }]
        : [{ op: 'remove_kv', key: item.argKey }]
    case 'kv_number':
      return next.trim() === ''
        ? [{ op: 'remove_kv', key: item.argKey }]
        : [{ op: 'set_kv', key: item.argKey, value: next.trim() }]
    case 'dtoverlay_toggle':
      return next === 'on'
        ? [...(item.extraOn ?? []), { op: 'add_dtoverlay', name: item.token }]
        : [{ op: 'remove_dtoverlay', name: item.token }]
    case 'dtoverlay_select': {
      const ops: BootOp[] = [{ op: 'remove_dtoverlay', name: item.token }]
      if (next) {
        ops.unshift(...(item.extraOn ?? []))
        ops.push({
          op: 'add_dtoverlay',
          name: item.token,
          params: (item.paramTemplate ?? '{v}').replace('{v}', next),
        })
      }
      return ops
    }
    default:
      return []
  }
}
