/** Pure diff of two external firmware files' detected properties.
 *
 * Both files already carry their inspected metadata + baked-in `config` in the
 * list response (see the backend `external_firmware` inspector), so a comparison
 * is a plain client-side diff — no extra request, no re-reading the binary.
 * Read-only: comparing never mutates either file.
 */

import type { ExternalFirmware } from './types'

/** How a single field differs between file A and file B. */
export type DiffStatus = 'same' | 'changed' | 'a_only' | 'b_only'

/** One compared field: its value in A, its value in B, and how they relate. */
export interface DiffRow {
  key: string
  a: string | null
  b: string | null
  status: DiffStatus
}

export interface FirmwareComparison {
  /** App / version / MCU / size (each file always has the slot; value may be null). */
  meta: DiffRow[]
  /** Union of both files' baked-in `config` keys, sorted. */
  config: DiffRow[]
  /** Tally over the `config` rows (the meaningful build-setting diff). */
  counts: Record<DiffStatus, number>
}

function status(a: string | null, b: string | null): DiffStatus {
  if (a !== null && b !== null) return a === b ? 'same' : 'changed'
  if (a !== null) return 'a_only'
  if (b !== null) return 'b_only'
  return 'same'
}

/** The metadata fields compared, in display order. */
const META_FIELDS: { key: string; get: (f: ExternalFirmware) => string | null }[] = [
  { key: 'app', get: (f) => f.detected_app },
  { key: 'version', get: (f) => f.detected_version },
  { key: 'mcu', get: (f) => f.detected_mcu },
  { key: 'size', get: (f) => (f.size ? String(f.size) : null) },
]

/** Diffs two firmware files into metadata + config rows with per-field status. */
export function compareFirmware(a: ExternalFirmware, b: ExternalFirmware): FirmwareComparison {
  const meta: DiffRow[] = META_FIELDS.map(({ key, get }) => {
    const av = get(a)
    const bv = get(b)
    return { key, a: av, b: bv, status: status(av, bv) }
  })

  const ac = a.detected_config ?? {}
  const bc = b.detected_config ?? {}
  const keys = [...new Set([...Object.keys(ac), ...Object.keys(bc)])].sort((x, y) =>
    x.localeCompare(y),
  )
  const config: DiffRow[] = keys.map((key) => {
    const av = key in ac ? ac[key] : null
    const bv = key in bc ? bc[key] : null
    return { key, a: av, b: bv, status: status(av, bv) }
  })

  const counts: Record<DiffStatus, number> = { same: 0, changed: 0, a_only: 0, b_only: 0 }
  for (const row of config) counts[row.status]++

  return { meta, config, counts }
}
