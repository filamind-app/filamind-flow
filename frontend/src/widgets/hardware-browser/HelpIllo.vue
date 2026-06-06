<script setup lang="ts">
/** Neutral teaching illustrations for the Hardware Browser help — one per HelpIlloKey.
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
    <!-- Magnifier -->
    <g v-if="illo === 'search'">
      <circle cx="10" cy="10" r="6" />
      <line x1="14.5" y1="14.5" x2="21" y2="21" />
    </g>

    <!-- Category grid -->
    <g v-else-if="illo === 'category'">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </g>

    <!-- IC chip -->
    <g v-else-if="illo === 'chip'">
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <path d="M4 10 h3 M4 14 h3 M17 10 h3 M17 14 h3 M10 4 v3 M14 4 v3 M10 17 v3 M14 17 v3" />
    </g>
  </svg>
</template>
