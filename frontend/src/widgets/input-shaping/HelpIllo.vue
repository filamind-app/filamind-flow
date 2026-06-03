<script setup lang="ts">
/** Neutral teaching illustrations for the help notes — one per HelpIlloKey. Same
 *  dependency-free recipe as DiagnosticIllo (24×24, currentColor), but these explain
 *  a concept rather than flag a problem, so they live separately. Kept to ≤6 strokes.
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
    <!-- Capture → analyze → apply flow -->
    <g v-if="illo === 'flow'">
      <rect x="3" y="9" width="5" height="6" />
      <rect x="16" y="9" width="5" height="6" />
      <line x1="9.5" y1="12" x2="14.5" y2="12" />
      <path d="M13 10 l2 2 l-2 2" />
    </g>

    <!-- Resonance peak above a baseline -->
    <g v-else-if="illo === 'peak'">
      <line x1="3" y1="19" x2="21" y2="19" />
      <path d="M4 17 L9 16 L12 5 L15 16 L20 17" />
    </g>

    <!-- Input-shaper impulse train -->
    <g v-else-if="illo === 'shaper'">
      <line x1="3" y1="19" x2="21" y2="19" />
      <line x1="7" y1="19" x2="7" y2="7" />
      <line x1="12" y1="19" x2="12" y2="12" />
      <line x1="17" y1="19" x2="17" y2="10" />
    </g>

    <!-- Noisy idle signal -->
    <g v-else-if="illo === 'noise'">
      <path d="M3 12 l2 -3 l2 5 l2 -6 l2 7 l2 -5 l2 4 l2 -3 l2 2" />
    </g>

    <!-- Two belts / pulleys for the CoreXY comparison -->
    <g v-else-if="illo === 'belt'">
      <circle cx="7" cy="12" r="3.5" />
      <circle cx="17" cy="12" r="3.5" />
      <line x1="7" y1="8.5" x2="17" y2="8.5" />
      <line x1="7" y1="15.5" x2="17" y2="15.5" />
    </g>

    <!-- Accelerometer chip with axis arrows -->
    <g v-else-if="illo === 'sensor'">
      <rect x="9" y="9" width="9" height="9" />
      <line x1="6" y1="18" x2="6" y2="6" />
      <path d="M4 8 l2 -2 l2 2" />
      <line x1="6" y1="18" x2="18" y2="18" />
      <path d="M16 16 l2 2 l-2 2" />
    </g>

    <!-- Speed sweep — rising bars -->
    <g v-else>
      <line x1="3" y1="20" x2="21" y2="20" />
      <line x1="6" y1="20" x2="6" y2="16" />
      <line x1="11" y1="20" x2="11" y2="12" />
      <line x1="16" y1="20" x2="16" y2="8" />
      <line x1="20" y1="20" x2="20" y2="4" />
    </g>
  </svg>
</template>
