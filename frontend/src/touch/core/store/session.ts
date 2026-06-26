// Pinia store mirroring the core FilaMindSession Observables into Vue refs (app-lifetime
// subscriptions) + the derived trust state the UI dims on. Mirrors the FilaMind screen store.
import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'
import type { PrinterObjects, KlippyState, PromptEvent } from '@filamind-app/core'
import { session } from '../session'

export type TrustState = 'live' | 'stale' | 'shutdown' | 'error' | 'offline'

export const useSessionStore = defineStore('touchSession', () => {
  const objects = shallowRef<PrinterObjects>(session.printer.objects.value)
  const klippy = ref<KlippyState>(session.klippy.value)
  const live = ref<boolean>(session.live.value)
  const prompt = shallowRef<PromptEvent>(session.prompt.value)

  session.printer.objects.subscribe((v) => (objects.value = v))
  session.klippy.subscribe((v) => (klippy.value = v))
  session.live.subscribe((v) => (live.value = v))
  session.prompt.subscribe((v) => (prompt.value = v))

  const klippyReady = computed(() => klippy.value === 'ready')

  const trust = computed<TrustState>(() => {
    if (klippy.value === 'shutdown') return 'shutdown'
    if (klippy.value === 'error') return 'error'
    if (live.value) return 'live'
    if (klippy.value === 'disconnected') return 'offline'
    return 'stale'
  })

  function object<T = Record<string, unknown>>(name: string): T | undefined {
    return objects.value[name] as T | undefined
  }

  let started = false
  async function start(): Promise<void> {
    if (started) return
    started = true
    await session.start()
  }

  return { objects, klippy, live, prompt, klippyReady, trust, object, start }
})
