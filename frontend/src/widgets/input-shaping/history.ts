/** A small, browser-local calibration history (localStorage) so you can see how
 *  an axis's recommended shaper / frequency drifts over time. Frontend-only — no
 *  backend or printer needed.
 */

export interface HistoryEntry {
  /** ISO timestamp of the calibration. */
  at: string
  axis: string | null
  shaper: string
  freq: number
}

const KEY = 'filamind.input-shaping.history'
const CAP = 20

/** Reads the saved history (newest first), tolerating missing/corrupt storage. */
export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(KEY)
    const data = raw ? JSON.parse(raw) : []
    return Array.isArray(data) ? (data as HistoryEntry[]) : []
  } catch {
    return []
  }
}

/** Prepends an entry, caps the list, persists it, and returns the new list. */
export function addHistory(entry: HistoryEntry): HistoryEntry[] {
  const next = [entry, ...loadHistory()].slice(0, CAP)
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable (private mode / quota) — keep the in-memory list */
  }
  return next
}

/** Clears the saved history. */
export function clearHistory(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
