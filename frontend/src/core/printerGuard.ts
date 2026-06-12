import { reactive } from 'vue'

import { resolveEndpoints } from '@/core/moonraker'

/** Global printer-guard state: is the printer printing, and does an actuating operation hold
 *  the exclusive slot? Polled once by the shell (AppHeader) and readable from any widget. */
export interface PrinterGuardState {
  /** Backend reachable on the last poll. */
  reachable: boolean
  /** Live print state: printing / paused / error / standby / ready / unknown. */
  printState: string
  /** An actuating operation currently holds the exclusive slot. */
  locked: boolean
  /** The running operation's stable key (e.g. `resonance_test`), when locked. */
  operation: string | null
  /** Writes (and motion) would be refused right now. */
  readonly writesBlocked: boolean
}

const state = reactive({
  reachable: true,
  printState: 'unknown',
  locked: false,
  operation: null as string | null,
  get writesBlocked(): boolean {
    return this.locked || ['printing', 'paused', 'error'].includes(this.printState)
  },
})

/** The shared, reactive guard state (singleton — every consumer sees the same object). */
export function usePrinterGuard(): PrinterGuardState {
  return state
}

/** One poll of `/api/guard/status`. The shell calls this on an interval; a widget can call it
 *  right before showing a gated confirm for a fresher answer. */
export async function refreshGuard(): Promise<void> {
  try {
    const { backendUrl } = resolveEndpoints()
    const response = await fetch(`${backendUrl}/api/guard/status`)
    if (!response.ok) throw new Error(String(response.status))
    const body = (await response.json()) as {
      locked: boolean
      operation: string | null
      print_state: string
      reachable: boolean
    }
    state.locked = body.locked
    state.operation = body.operation
    state.printState = body.print_state
    state.reachable = body.reachable
  } catch {
    state.reachable = false
  }
}
