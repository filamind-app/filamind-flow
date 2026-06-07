/** In-widget cross-entity navigation for the Hardware Browser.
 *
 * A clickable cross-link chip (RelatedChips) calls `focusEntity(...)`; the widget watches the
 * shared `focus` ref to switch to the right tab, and the destination panel watches it to open the
 * targeted entity. Keeps the panels decoupled (no parent prop-drilling) while letting any node
 * jump to any related node. */
import { ref } from 'vue'

import type { RelatedRef } from './types'

/** The tab a graph entity lives under. */
export type EntityTab =
  | 'boards'
  | 'drivers'
  | 'motors'
  | 'hosts'
  | 'manufacturers'
  | 'mcus'
  | 'category'

export interface FocusTarget {
  tab: EntityTab
  id: string
  name?: string
  /** Only set for catalog entities — the category whose panel hosts them. */
  category?: string
}

/** Maps the singular graph `type` (from a RelatedRef) to its hosting tab. */
const TYPE_TO_TAB: Record<string, EntityTab> = {
  board: 'boards',
  driver: 'drivers',
  motor: 'motors',
  host: 'hosts',
  manufacturer: 'manufacturers',
  mcu: 'mcus',
  catalog: 'category',
}

/** A relation is navigable only if we know which tab its target lives under. */
export function targetFor(ref: RelatedRef): FocusTarget | null {
  const tab = TYPE_TO_TAB[ref.type]
  if (!tab || !ref.id) return null
  return {
    tab,
    id: ref.id,
    name: ref.name ?? undefined,
    category: ref.category,
  }
}

const focus = ref<FocusTarget | null>(null)

export function useEntityFocus() {
  return {
    focus,
    focusEntity(target: FocusTarget): void {
      // reassign a fresh object so a repeat click on the same entity still triggers watchers
      focus.value = { ...target }
    },
    clear(): void {
      focus.value = null
    },
  }
}
