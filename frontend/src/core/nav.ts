import { ref } from 'vue'

/**
 * App-wide view switch (a tiny router stand-in — the app ships no vue-router).
 *
 * ``current`` is either ``'dashboard'`` (the empty home) or a widget id. The
 * sidebar sets it; the shell renders the matching page. A module-level ref keeps
 * it a single shared singleton across every component that calls ``useNav()``.
 */
const current = ref<string>('dashboard')

export function useNav() {
  return {
    current,
    go(view: string): void {
      current.value = view
    },
  }
}
