/** Turns a streaming flash log into a phase-based progress view.
 *
 *  The backend emits machine-readable `::phase::<code>` markers alongside the human `>>> …`
 *  lines. This module parses those (and the `!!` error lines) into a compact status the UI
 *  renders as a progress bar instead of a raw command window — while keeping the full log for
 *  a collapsible details view. Pure + testable; the component owns all rendering and i18n.
 */

/** Ordered flash phases. `start` and `done` bracket the run; `error` is terminal. */
export const FLASH_PHASES = ['start', 'stop', 'boot', 'write', 'restart', 'done'] as const
export type FlashPhase = (typeof FLASH_PHASES)[number]

const PHASE_RE = /^::phase::(\w+)\s*$/
/** A line that is a genuine failure (the backend marks these with `!!`). */
const ERROR_RE = /^!!\s?(.*)$/

export interface FlashStatus {
  /** The furthest phase reached, or null before the first marker. */
  phase: FlashPhase | null
  /** 0..1 progress for the bar: phase position, full on done, frozen-in-place on error. */
  fraction: number
  /** Real failure lines (without the `!!` prefix), in order. Empty = no errors. */
  errors: string[]
  /** Whether the run finished successfully (reached `done` with no errors). */
  done: boolean
  /** Whether the run failed (an error line appeared). */
  failed: boolean
}

/** The log with the machine `::phase::` markers stripped — what the details view shows. */
export function stripPhaseMarkers(log: string): string {
  return log
    .split('\n')
    .filter((line) => !PHASE_RE.test(line))
    .join('\n')
}

/** Parse the accumulated log into a {@link FlashStatus}. `running` keeps the bar from
 *  reading as "complete" before the stream actually ends (a paused mid-phase stream). */
export function parseFlashStatus(log: string, running: boolean): FlashStatus {
  let phaseIndex = -1
  const errors: string[] = []
  for (const line of log.split('\n')) {
    const pm = PHASE_RE.exec(line)
    if (pm) {
      const idx = (FLASH_PHASES as readonly string[]).indexOf(pm[1])
      if (idx > phaseIndex) phaseIndex = idx
      continue
    }
    const em = ERROR_RE.exec(line)
    if (em) errors.push(em[1].trim())
  }
  const phase = phaseIndex >= 0 ? FLASH_PHASES[phaseIndex] : null
  const failed = errors.length > 0
  const done = phase === 'done' && !failed
  // Fraction: position along the phase list. Done → full; error → hold at current spot;
  // otherwise the phase index over the number of forward phases (start counts as a step).
  let fraction: number
  if (done) fraction = 1
  else if (phaseIndex < 0) fraction = failed ? 0 : 0.02
  else fraction = Math.min(0.95, (phaseIndex + 1) / FLASH_PHASES.length)
  // A still-running stream never shows a full bar until `done` is seen.
  if (running && !done) fraction = Math.min(fraction, 0.95)
  return { phase, fraction, errors, done, failed }
}
