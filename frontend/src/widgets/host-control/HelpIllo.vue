<script setup lang="ts">
/** Neutral teaching illustrations for the Host Control help notes — one per HelpIlloKey.
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
    <!-- Host: a single-board computer with a chip and pin header -->
    <g v-if="illo === 'host'">
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <rect x="7" y="9" width="6" height="6" rx="1" />
      <line x1="16" y1="9" x2="18" y2="9" />
      <line x1="16" y1="12" x2="18" y2="12" />
      <line x1="16" y1="15" x2="18" y2="15" />
    </g>

    <!-- Monitor: a gauge / health dial with a needle -->
    <g v-else-if="illo === 'monitor'">
      <path d="M4 16 a8 8 0 0 1 16 0" />
      <line x1="12" y1="16" x2="16" y2="11" />
      <circle cx="12" cy="16" r="1.3" fill="currentColor" stroke="none" />
      <line x1="6.5" y1="13.5" x2="7.5" y2="14.2" stroke-opacity="0.5" />
      <line x1="17.5" y1="13.5" x2="16.5" y2="14.2" stroke-opacity="0.5" />
    </g>

    <!-- Services: a stack of toggleable rows (gears would over-crowd) -->
    <g v-else>
      <rect x="3" y="4" width="18" height="4.5" rx="1" />
      <rect x="3" y="10" width="18" height="4.5" rx="1" />
      <rect x="3" y="16" width="18" height="4.5" rx="1" />
      <circle cx="7" cy="6.25" r="1" fill="currentColor" stroke="none" />
      <circle cx="7" cy="12.25" r="1" fill="currentColor" stroke="none" />
      <circle cx="7" cy="18.25" r="1" fill="currentColor" stroke="none" stroke-opacity="0.4" />
    </g>
  </svg>
</template>
