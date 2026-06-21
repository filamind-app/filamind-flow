<script setup lang="ts">
/** Neutral teaching illustrations for the Material Brain help - one per HelpIlloKey.
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
    <!-- Material: a filament spool -->
    <g v-if="illo === 'material'">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M12 4 v3.5 M20 12 h-3.5" stroke-opacity="0.6" />
    </g>

    <!-- Flow: filament through a nozzle, a drop below -->
    <g v-else-if="illo === 'flow'">
      <path d="M9 4 h6 l-1.5 9 h-3 z" />
      <path d="M10.5 13 l1.5 3 l1.5 -3" />
      <path d="M12 19 a1.4 1.4 0 1 0 0.01 0" />
    </g>
  </svg>
</template>
