<script setup lang="ts">
/** Neutral teaching illustrations for the Max-Flow help — one per HelpIlloKey.
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
    <!-- Molten filament flowing out of a nozzle -->
    <g v-if="illo === 'flow'">
      <path d="M8 3 h8 v6 l-3 4 v5 h-2 v-5 l-3 -4 Z" />
      <path d="M11 19 q1 2 1 2 q0 -0 1 -2" />
    </g>

    <!-- StallGuard load: a steady trace that turns erratic -->
    <g v-else-if="illo === 'stallguard'">
      <path d="M3 12 h6" />
      <path d="M9 12 l2 -5 l2 9 l2 -7 l2 6 l2 -3 h2" />
    </g>

    <!-- Slipping hobbed gear (teeth + a skid arrow) -->
    <g v-else-if="illo === 'slip'">
      <circle cx="9" cy="12" r="5" />
      <path d="M9 7 v2 M9 15 v2 M4 12 h2 M12 12 h2" />
      <path d="M16 9 h5 M19 7 l2 2 l-2 2" />
    </g>

    <!-- Safety: heat + a warning triangle -->
    <g v-else-if="illo === 'safety'">
      <path d="M7 4 q-2 2 0 4 t0 4 M12 4 q-2 2 0 4 t0 4" />
      <path d="M16 13 l5 8 h-10 Z" />
      <path d="M16 16 v3" />
    </g>
  </svg>
</template>
