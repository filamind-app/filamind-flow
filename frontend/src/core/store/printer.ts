import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'

import { moonraker } from '@/core/moonraker'
import type { ConnectionState, PrinterObjectStatus } from '@/core/moonraker'
import { widgetRegistry } from '@/core/registry'

/**
 * Central reactive mirror of Moonraker state. Widgets read from here instead of
 * touching the socket, so there is a single source of truth and a single
 * subscription shared across the whole dashboard.
 */
export const usePrinterStore = defineStore('printer', () => {
  const connectionState = ref<ConnectionState>('idle')
  const status = shallowRef<PrinterObjectStatus>({})
  let initialised = false

  /** Shallow-merges a status delta into the reactive snapshot. */
  function mergeStatus(update: PrinterObjectStatus): void {
    const next: PrinterObjectStatus = { ...status.value }
    for (const [object, fields] of Object.entries(update)) {
      next[object] = { ...(next[object] ?? {}), ...fields }
    }
    status.value = next
  }

  /** Subscribes to the union of every registered widget's printer objects. */
  async function subscribeForWidgets(): Promise<void> {
    const objects = widgetRegistry.aggregateSubscriptions()
    if (Object.keys(objects).length === 0) return
    const initial = await moonraker.subscribeObjects(objects)
    mergeStatus(initial)
  }

  /** Wires listeners and opens the connection. Idempotent. */
  function init(): void {
    if (initialised) return
    initialised = true

    moonraker.onStateChange((state) => {
      connectionState.value = state
      if (state === 'connected') void subscribeForWidgets()
    })

    moonraker.onNotification('notify_status_update', (params) => {
      // Moonraker sends [status, eventtime]; we only need the status delta.
      if (Array.isArray(params) && params[0]) {
        mergeStatus(params[0] as PrinterObjectStatus)
      }
    })

    moonraker.connect()
  }

  return { connectionState, status, init, subscribeForWidgets, mergeStatus }
})
