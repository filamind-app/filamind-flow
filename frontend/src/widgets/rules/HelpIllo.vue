<script setup lang="ts">
/** Neutral teaching illustrations for the Rules help. Dependency-free 24x24 line art. */
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
    <!-- Rule: IF -> THEN (two boxes joined by an arrow) -->
    <g v-if="illo === 'rule'">
      <rect x="3" y="8" width="7" height="8" rx="1" />
      <rect x="14" y="8" width="7" height="8" rx="1" />
      <path d="M10 12 h4 M12.5 10.5 L14 12 L12.5 13.5" />
    </g>

    <!-- Safe: a shield with a check (opt-in / guarded) -->
    <g v-else-if="illo === 'safe'">
      <path d="M12 3 l7 3 v5 c0 4.5 -3 7.5 -7 9 c-4 -1.5 -7 -4.5 -7 -9 V6 Z" />
      <path d="M9 12 l2 2 l4 -4" stroke-opacity="0.7" />
    </g>
  </svg>
</template>
