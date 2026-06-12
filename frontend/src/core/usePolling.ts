import { onMounted, onUnmounted } from 'vue'

/** Poll `fn` every `ms` while the component is mounted, skipping ticks when the tab is hidden
 *  (no point hammering the printer host from a background tab). Runs once immediately. */
export function usePolling(fn: () => void | Promise<void>, ms: number): void {
  let timer: number | undefined

  const tick = (): void => {
    if (typeof document === 'undefined' || !document.hidden) void fn()
  }

  onMounted(() => {
    tick()
    timer = window.setInterval(tick, ms)
  })
  onUnmounted(() => {
    if (timer !== undefined) window.clearInterval(timer)
  })
}
