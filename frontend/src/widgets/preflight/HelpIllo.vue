<script setup lang="ts">
/** Neutral teaching illustrations for the Preflight help - one per HelpIlloKey.
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
    <!-- Gate: a barrier that lifts once checks pass -->
    <g v-if="illo === 'gate'">
      <line x1="4" y1="20" x2="20" y2="20" />
      <rect x="5" y="9" width="3" height="11" />
      <line x1="8" y1="11" x2="20" y2="6" />
      <circle cx="18" cy="12" r="2.5" stroke-opacity="0.7" />
    </g>

    <!-- Check: a checklist with a tick -->
    <g v-else-if="illo === 'check'">
      <rect x="5" y="3" width="14" height="18" rx="1.5" />
      <path d="M8 8 l1.5 1.5 l3 -3" />
      <line x1="14" y1="8" x2="16.5" y2="8" stroke-opacity="0.7" />
      <path d="M8 14 l1.5 1.5 l3 -3" />
      <line x1="14" y1="14" x2="16.5" y2="14" stroke-opacity="0.7" />
    </g>
  </svg>
</template>
