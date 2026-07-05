/** Persists an in-progress Guided tune so it survives navigating to another widget or an
 *  accidental page refresh - and is dropped only when the tune finishes.
 *
 *  The whole wizard lives in component-local reactive state (GuidedTune.vue), which Vue discards
 *  when the widget unmounts (there is no <keep-alive>) or on a full reload. This module mirrors the
 *  app's hand-rolled localStorage idiom (best-effort try/catch, like theme.ts / max-flow's
 *  LAST_RESULT_KEY): the wizard writes a snapshot on every change and restores it on mount. It
 *  stores the accumulated JOURNEY (captured results already survive server-side in the archive; the
 *  wizard's step/verdicts/suggestions do not), so a resumed session never re-runs finished stages.
 */

import type { Gate, StepId, StepState } from './guided'
import type { Suggestion } from './recommend'
import type { BeltComparison, NoiseResult, ShaperAnalysis, VibrationsProfile } from './types'

const STORAGE_KEY = 'filamind-guided-tune'
/** Bump to invalidate snapshots written by an older, incompatible shape. */
const SCHEMA = 1

/** The durable slice of the wizard - everything needed to resume where the user left off. The
 *  transient bits (busy / error / the motion-ready checkbox) are intentionally NOT persisted. */
export interface GuidedSnapshot {
  idx: number
  statuses: Partial<Record<StepId, StepState>>
  results: {
    noise?: NoiseResult
    belts?: BeltComparison
    shaperX?: ShaperAnalysis
    shaperY?: ShaperAnalysis
    vibrations?: VibrationsProfile
  }
  verdicts: Partial<Record<StepId, Gate>>
  sugg: Partial<Record<StepId, Suggestion[]>>
  archived: Partial<Record<StepId, boolean>>
  openCards: Partial<Record<StepId, boolean>>
  kinematics: string | null
}

interface StoredSnapshot extends GuidedSnapshot {
  v: number
}

/** Write the current wizard state (best-effort: private mode / quota errors are swallowed). */
export function saveGuidedSession(snapshot: GuidedSnapshot): void {
  try {
    const stored: StoredSnapshot = { v: SCHEMA, ...snapshot }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
  } catch {
    // Persistence is a convenience - if the browser refuses, the tune still works, just unsaved.
  }
}

/** Read a saved wizard session, or null if none / unreadable / from an incompatible schema. */
export function loadGuidedSession(): GuidedSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const stored = JSON.parse(raw) as StoredSnapshot
    // Reject anything that isn't a coherent v1 snapshot (wrong/absent schema, or a malformed write
    // missing the core sub-objects the restore assigns from) rather than half-restoring it.
    const isObj = (x: unknown): boolean => typeof x === 'object' && x !== null
    if (
      !stored ||
      stored.v !== SCHEMA ||
      typeof stored.idx !== 'number' ||
      !isObj(stored.statuses) ||
      !isObj(stored.results) ||
      !isObj(stored.verdicts) ||
      !isObj(stored.sugg) ||
      !isObj(stored.archived) ||
      !isObj(stored.openCards)
    )
      return null
    // Return the wizard slice without the schema marker.
    return {
      idx: stored.idx,
      statuses: stored.statuses,
      results: stored.results,
      verdicts: stored.verdicts,
      sugg: stored.sugg,
      archived: stored.archived,
      openCards: stored.openCards,
      kinematics: stored.kinematics,
    }
  } catch {
    return null
  }
}

/** Drop the saved session (on completion). Best-effort. */
export function clearGuidedSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}
