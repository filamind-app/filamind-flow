<script setup lang="ts">
/** Neutral teaching illustrations for the Macro Designer help — one per HelpIlloKey.
 *  Dependency-free 24×24 line art (currentColor), ≤6 strokes each, theme-aware.
 */
import type { HelpIlloKey } from './help'

defineProps<{ illo: HelpIlloKey }>()
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    role="img"
    aria-hidden="true"
  >
    <!-- A toolhead path (zig-zag with a node) -->
    <g v-if="illo === 'path'">
      <path d="M3 18 L8 6 L13 18 L18 8 L21 14" />
      <circle cx="3" cy="18" r="1.2" />
    </g>

    <!-- G-code lines on a page -->
    <g v-else-if="illo === 'gcode'">
      <rect x="4" y="3" width="16" height="18" rx="1" />
      <path d="M7 8 h7 M7 12 h10 M7 16 h6" />
    </g>

    <!-- A macro: a labelled block expanding into commands -->
    <g v-else-if="illo === 'macro'">
      <rect x="3" y="4" width="8" height="5" rx="1" />
      <path d="M11 6.5 h4" />
      <path d="M15 6.5 l-2 -1.5 M15 6.5 l-2 1.5" />
      <path d="M15 11 h6 M15 15 h6 M15 19 h6" />
    </g>
  </svg>
</template>
