<script setup lang="ts">
/** Neutral teaching illustrations for the Config Editor help — one per HelpIlloKey.
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
    <!-- A config file with text lines -->
    <g v-if="illo === 'file'">
      <path d="M6 3 h8 l4 4 v14 a0 0 0 0 1 0 0 H6 Z" />
      <line x1="9" y1="11" x2="15" y2="11" />
      <line x1="9" y1="15" x2="15" y2="15" />
    </g>

    <!-- A [section] header with two parameter rows under it -->
    <g v-else-if="illo === 'section'">
      <rect x="3" y="3" width="18" height="6" rx="1" />
      <line x1="6" y1="14" x2="11" y2="14" />
      <line x1="14" y1="14" x2="18" y2="14" />
      <line x1="6" y1="18" x2="11" y2="18" />
      <line x1="14" y1="18" x2="18" y2="18" />
    </g>

    <!-- One file pulling in another (include) -->
    <g v-else-if="illo === 'include'">
      <rect x="3" y="4" width="9" height="11" rx="1" />
      <rect x="12" y="9" width="9" height="11" rx="1" />
      <path d="M9 9 h5" />
      <path d="M12 7 l2 2 l-2 2" />
    </g>

    <!-- A warning triangle (validation issue) -->
    <g v-else-if="illo === 'validation'">
      <path d="M12 4 L21 19 H3 Z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <line x1="12" y1="16.5" x2="12" y2="16.5" />
    </g>

    <!-- A locked/auto block (SAVE_CONFIG) -->
    <g v-else-if="illo === 'saveConfig'">
      <rect x="4" y="10" width="16" height="10" rx="1" />
      <path d="M8 10 V7 a4 4 0 0 1 8 0 v3" />
    </g>
  </svg>
</template>
