<script setup lang="ts">
/** Neutral teaching illustrations for the Board Topology help — one per HelpIlloKey.
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
    <!-- Host SBC: a small board with a header -->
    <g v-if="illo === 'host'">
      <rect x="3" y="6" width="18" height="12" rx="1" />
      <path d="M6 6 V4 M10 6 V4 M14 6 V4" />
      <circle cx="8" cy="12" r="1.5" />
    </g>

    <!-- MCU chip: a square IC with pins -->
    <g v-else-if="illo === 'mcu'">
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <path d="M4 10 h3 M4 14 h3 M17 10 h3 M17 14 h3 M10 4 v3 M14 4 v3 M10 17 v3 M14 17 v3" />
    </g>

    <!-- CAN bus: two nodes on a shared line -->
    <g v-else-if="illo === 'canbus'">
      <path d="M3 16 h18" />
      <rect x="5" y="6" width="5" height="5" rx="1" />
      <rect x="14" y="6" width="5" height="5" rx="1" />
      <path d="M7.5 11 v5 M16.5 11 v5" />
    </g>
  </svg>
</template>
