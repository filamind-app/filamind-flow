<script setup lang="ts">
/** Neutral teaching illustrations for the Known-Good Pack help - one per HelpIlloKey.
 *  Dependency-free 24x24 line art (currentColor), theme-aware.
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
    <!-- Pack: a box/archive of saved files with a check -->
    <g v-if="illo === 'pack'">
      <path d="M4 7 h16 v12 a1 1 0 0 1 -1 1 H5 a1 1 0 0 1 -1 -1 Z" />
      <path d="M3 4 h18 v3 H3 Z" />
      <path d="M9 12 l2 2 l4 -4" stroke-opacity="0.7" />
    </g>

    <!-- Restore: a counter-clockwise arrow (roll back) -->
    <g v-else-if="illo === 'restore'">
      <path d="M5 8 a8 8 0 1 1 -1.5 6" />
      <path d="M5 4 V8 H9" />
    </g>
  </svg>
</template>
