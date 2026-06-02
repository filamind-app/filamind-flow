<script setup lang="ts">
/** Hand-drawn line illustrations for the resonance diagnostics — one per IlloKey.
 *  Dependency-free inline SVG, stroked with `currentColor` so the parent tints it
 *  by severity. 24×24 viewBox; size via a width/height class on the element.
 */
import type { IlloKey } from './diagnose'

defineProps<{ illo: IlloKey }>()
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
    <!-- Belt + pulleys → tension / soft axis -->
    <g v-if="illo === 'belt'">
      <circle cx="7" cy="12" r="3.5" />
      <circle cx="17" cy="12" r="3.5" />
      <line x1="7" y1="8.5" x2="17" y2="8.5" />
      <line x1="7" y1="15.5" x2="17" y2="15.5" />
    </g>

    <!-- Gantry frame → rigidity -->
    <g v-else-if="illo === 'frame'">
      <rect x="4" y="4" width="16" height="16" />
      <line x1="4" y1="10" x2="20" y2="10" />
      <rect x="10" y="7.5" width="4" height="2.5" />
    </g>

    <!-- Printhead / hotend → loose toolhead -->
    <g v-else-if="illo === 'toolhead'">
      <path d="M8 5 H16 V11 L13 16 H11 L8 11 Z" />
      <line x1="12" y1="2.5" x2="12" y2="5" />
    </g>

    <!-- Accelerometer chip → sensor mount / noise -->
    <g v-else-if="illo === 'accel'">
      <rect x="7" y="7" width="10" height="10" />
      <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
      <line x1="5" y1="10" x2="7" y2="10" />
      <line x1="5" y1="14" x2="7" y2="14" />
      <line x1="17" y1="10" x2="19" y2="10" />
      <line x1="17" y1="14" x2="19" y2="14" />
    </g>

    <!-- Equaliser sliders → tuning (smoothing / accel) -->
    <g v-else-if="illo === 'tune'">
      <line x1="4" y1="8" x2="20" y2="8" />
      <circle cx="9" cy="8" r="2.2" fill="currentColor" stroke="none" />
      <line x1="4" y1="16" x2="20" y2="16" />
      <circle cx="15" cy="16" r="2.2" fill="currentColor" stroke="none" />
    </g>

    <!-- Unequal bars → X/Y imbalance -->
    <g v-else-if="illo === 'balance'">
      <line x1="4" y1="18" x2="20" y2="18" />
      <line x1="8" y1="18" x2="8" y2="7" />
      <line x1="6" y1="7" x2="10" y2="7" />
      <line x1="16" y1="18" x2="16" y2="12" />
      <line x1="14" y1="12" x2="18" y2="12" />
    </g>

    <!-- Checkmark → healthy -->
    <path v-else d="M5 13 l4 4 l10 -11" />
  </svg>
</template>
