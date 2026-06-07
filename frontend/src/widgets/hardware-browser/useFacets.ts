/** Shared catalog facet options (boardClass / nema / kind), fetched once and reused by every
 *  panel that exposes a facet dropdown. */
import { ref } from 'vue'

import { fetchFacets } from './api'
import type { HardwareFacets } from './types'

const facets = ref<HardwareFacets | null>(null)
let started = false

export function useFacets() {
  if (!started) {
    started = true
    void fetchFacets()
      .then((f) => {
        facets.value = f
      })
      .catch(() => {
        started = false // allow a later panel to retry
      })
  }
  return { facets }
}
