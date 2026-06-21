<script setup lang="ts">
/** Neutral teaching illustrations for the Tuning help - one per HelpIlloKey.
 *  Dependency-free 24×24 line art (currentColor), theme-aware.
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
    <!-- Tower: a stack of layers (the tuning tower) with an up arrow -->
    <g v-if="illo === 'tower'">
      <rect x="7" y="14" width="10" height="3" />
      <rect x="7" y="10" width="10" height="3" />
      <rect x="7" y="6" width="10" height="3" />
      <path d="M12 6 V3 M10.5 4.5 L12 3 L13.5 4.5" stroke-opacity="0.7" />
    </g>

    <!-- Apply: a slider/dial settling on a value with a check -->
    <g v-else-if="illo === 'apply'">
      <line x1="4" y1="9" x2="20" y2="9" />
      <circle cx="14" cy="9" r="2.2" fill="currentColor" stroke="none" />
      <path d="M5 16 l3 3 l6 -7" />
    </g>

    <!-- Retraction: a nozzle pulling filament back (up arrow into the hotend) -->
    <g v-else-if="illo === 'retraction'">
      <path d="M9 4 h6 l-1.5 9 h-3 Z" />
      <path d="M10.5 13 l1.5 4 l1.5 -4" />
      <path d="M12 11 V5 M10.5 6.5 L12 5 L13.5 6.5" stroke-opacity="0.7" />
    </g>
  </svg>
</template>
