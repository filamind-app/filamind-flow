<script setup lang="ts">
/** Teaching illustrations for the Firmware Upgrade help notes — dependency-free 24×24 line
 *  art (currentColor), ≤6 strokes each, theme-aware. One per HelpIlloKey.
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
    <!-- A microcontroller chip with pins -->
    <g v-if="illo === 'mcu'">
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <line x1="4" y1="10" x2="7" y2="10" />
      <line x1="4" y1="14" x2="7" y2="14" />
      <line x1="17" y1="10" x2="20" y2="10" />
      <line x1="17" y1="14" x2="20" y2="14" />
    </g>

    <!-- Flashing: a chip with a download arrow into it -->
    <g v-else-if="illo === 'flash'">
      <rect x="6" y="12" width="12" height="7" rx="1" />
      <line x1="12" y1="3" x2="12" y2="10" />
      <path d="M9 7 l3 3 l3 -3" />
    </g>

    <!-- Host ↔ MCU sync: two boxes with a two-way link -->
    <g v-else-if="illo === 'sync'">
      <rect x="3" y="9" width="6" height="6" />
      <rect x="15" y="9" width="6" height="6" />
      <path d="M10 10 l3 0 M14 10 l-1 -1 M14 10 l-1 1" />
      <path d="M14 14 l-3 0 M10 14 l1 -1 M10 14 l1 1" />
    </g>

    <!-- A wrench (toolchain) -->
    <g v-else>
      <path d="M16 4 a4 4 0 0 0 -5 5 l-7 7 l3 3 l7 -7 a4 4 0 0 0 5 -5 l-3 3 l-3 -3 z" />
    </g>
  </svg>
</template>
