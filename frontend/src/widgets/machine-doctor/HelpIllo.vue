<script setup lang="ts">
/** Neutral teaching illustrations for the Machine Doctor help drawer — one per HelpIlloKey.
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
    <!-- Doctor: a stethoscope -->
    <g v-if="illo === 'doctor'">
      <path d="M5 3 v5 a4 4 0 0 0 8 0 V3" />
      <path d="M9 16 a5 5 0 0 0 9 -3 v-2" />
      <circle cx="18" cy="9" r="2" />
    </g>

    <!-- Grade: a report card with an 'A' -->
    <g v-else-if="illo === 'grade'">
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M9 16 l2.5 -8 l2.5 8" />
      <line x1="9.7" y1="13.5" x2="13.3" y2="13.5" />
    </g>

    <!-- Fix: a wrench -->
    <g v-else>
      <path
        d="M15.5 7.5 a3.5 3.5 0 0 0 -4.6 4.3 l-6.2 6.2 a1.5 1.5 0 0 0 2.1 2.1 l6.2 -6.2 a3.5 3.5 0 0 0 4.3 -4.6 l-2.2 2.2 l-2.1 -2.1 z"
      />
    </g>
  </svg>
</template>
