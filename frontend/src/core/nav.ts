import { onMounted, ref, watch } from 'vue'

/**
 * App-wide view switch (a tiny router stand-in — the app ships no vue-router).
 *
 * ``current`` is either ``'dashboard'`` (the empty home) or a widget id. It is synced to
 * ``location.hash`` (#117/#121) so a view can be bookmarked and survives a reload — important
 * for the tablet-at-the-printer case. A module-level ref keeps it a single shared singleton
 * across every component that calls ``useNav()``.
 *
 * Deep links go one level further: ``#widget-id/tab`` opens a widget ON a tab (e.g.
 * ``#firmware-upgrade/status``). The tab half is parked in ``pendingTab`` and consumed by the
 * target widget via :func:`useHashTab`, so cross-widget jumps can land on the exact view.
 */
function parseHash(): { view: string; tab: string | null } {
  const h = window.location.hash.replace(/^#\/?/, '').trim()
  if (!h) return { view: 'dashboard', tab: null }
  const slash = h.indexOf('/')
  if (slash === -1) return { view: h, tab: null }
  return { view: h.slice(0, slash), tab: h.slice(slash + 1) || null }
}

const initial = parseHash()
const current = ref<string>(initial.view)
/** A tab requested for a widget (by hash or ``go(view, tab)``) that it hasn't consumed yet. */
const pendingTab = ref<{ view: string; tab: string } | null>(
  initial.tab ? { view: initial.view, tab: initial.tab } : null,
)
/** Whether the off-canvas sidebar is open on narrow screens (no effect at ``md`` and up). */
const sidebarOpen = ref(false)

// Back/forward and manual hash edits update the view (and park any tab half).
window.addEventListener('hashchange', () => {
  const parsed = parseHash()
  if (parsed.view !== current.value) current.value = parsed.view
  if (parsed.tab) pendingTab.value = { view: parsed.view, tab: parsed.tab }
})

export function useNav() {
  return {
    current,
    sidebarOpen,
    go(view: string, tab?: string): void {
      current.value = view
      sidebarOpen.value = false // close the mobile drawer after navigating
      if (tab) pendingTab.value = { view, tab }
      if (view === 'dashboard') {
        // Clear the hash without leaving a bare '#' in the URL.
        history.replaceState(null, '', window.location.pathname + window.location.search)
      } else {
        const target = tab ? `${view}/${tab}` : view
        if (window.location.hash !== `#${target}`) window.location.hash = target
      }
    },
  }
}

/**
 * Let a tabbed widget land on a deep-linked tab. Call from the widget's setup with its id and
 * an applier that validates + sets its own tab/mode ref; runs on mount and on later jumps
 * (``go('widget', 'tab')`` while the widget is already open).
 */
export function useHashTab(widgetId: string, apply: (tab: string) => void): void {
  const consume = (): void => {
    const pending = pendingTab.value
    if (pending && pending.view === widgetId) {
      pendingTab.value = null
      apply(pending.tab)
    }
  }
  onMounted(consume)
  watch(pendingTab, consume)
}
