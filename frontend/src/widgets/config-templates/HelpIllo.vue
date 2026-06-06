<script setup lang="ts">
/** Neutral teaching illustrations for the Config Templates help — one per HelpIlloKey.
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
    <!-- A document/template with lines -->
    <g v-if="illo === 'template'">
      <path d="M6 3 h8 l4 4 v14 H6 Z" />
      <path d="M14 3 v4 h4" />
      <path d="M9 12 h6 M9 16 h6" />
    </g>

    <!-- Clipboard / paste -->
    <g v-else-if="illo === 'paste'">
      <rect x="5" y="5" width="14" height="16" rx="1" />
      <rect x="9" y="3" width="6" height="4" rx="1" />
      <path d="M9 12 h6 M9 16 h4" />
    </g>

    <!-- A [section] header block -->
    <g v-else-if="illo === 'section'">
      <rect x="3" y="4" width="18" height="6" rx="1" />
      <path d="M6 7 h5" />
      <path d="M6 14 h12 M6 18 h9" />
    </g>
  </svg>
</template>
