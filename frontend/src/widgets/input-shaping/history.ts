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
  /** Measurement quality grade (A–F) — optional for entries saved before v0.38. */
  grade?: string
  /** 0–100 quality score — optional for older entries. */
  score?: number
}

export type GradeTrend = 'up' | 'down' | 'same' | 'none'

export interface HistoryEntryWithTrend extends HistoryEntry {
  /** How this score compares to the previous calibration of the same axis. */
  trend: GradeTrend
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

/** Annotates each entry (newest-first) with how its score compares to the previous
 *  calibration of the *same axis* — so the effect of a mechanical fix is visible. */
export function withTrends(entries: HistoryEntry[]): HistoryEntryWithTrend[] {
  return entries.map((entry, i) => {
    if (entry.score == null) return { ...entry, trend: 'none' }
    // Newest-first, so the previous same-axis calibration is later in the list.
    const prev = entries.slice(i + 1).find((p) => p.axis === entry.axis && p.score != null)
    if (!prev || prev.score == null) return { ...entry, trend: 'none' }
    if (entry.score > prev.score) return { ...entry, trend: 'up' }
    if (entry.score < prev.score) return { ...entry, trend: 'down' }
    return { ...entry, trend: 'same' }
  })
}

/** Clears the saved history. */
export function clearHistory(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
