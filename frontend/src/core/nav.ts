import { ref } from 'vue'

/**
 * App-wide view switch (a tiny router stand-in — the app ships no vue-router).
 *
 * ``current`` is either ``'dashboard'`` (the empty home) or a widget id. It is synced to
 * ``location.hash`` (#117/#121) so a view can be bookmarked and survives a reload — important
 * for the tablet-at-the-printer case. A module-level ref keeps it a single shared singleton
 * across every component that calls ``useNav()``.
 */
function fromHash(): string {
  const h = window.location.hash.replace(/^#\/?/, '').trim()
  return h || 'dashboard'
}

const current = ref<string>(fromHash())
/** Whether the off-canvas sidebar is open on narrow screens (no effect at ``md`` and up). */
const sidebarOpen = ref(false)

// Back/forward and manual hash edits update the view.
window.addEventListener('hashchange', () => {
  const v = fromHash()
  if (v !== current.value) current.value = v
})

export function useNav() {
  return {
    current,
    sidebarOpen,
    go(view: string): void {
      current.value = view
      sidebarOpen.value = false // close the mobile drawer after navigating
      if (view === 'dashboard') {
        // Clear the hash without leaving a bare '#' in the URL.
        history.replaceState(null, '', window.location.pathname + window.location.search)
      } else if (window.location.hash !== `#${view}`) {
        window.location.hash = view
      }
    },
  }
}
