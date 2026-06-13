<script setup lang="ts">
/** Neutral teaching illustrations for the KlipperScreen Studio help notes — one per HelpIlloKey.
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
    <!-- Touchscreen: a framed display on a stand with a finger-tap dot -->
    <g v-if="illo === 'screen'">
      <rect x="3" y="3" width="18" height="13" rx="1.5" />
      <line x1="9" y1="20" x2="15" y2="20" />
      <line x1="12" y1="16" x2="12" y2="20" />
      <circle cx="12" cy="9.5" r="1.5" fill="currentColor" stroke="none" />
    </g>

    <!-- Config file: a document with text lines -->
    <g v-else-if="illo === 'config'">
      <path d="M6 3 h8 l4 4 v14 a0 0 0 0 1 0 0 H6 Z" />
      <line x1="9" y1="11" x2="15" y2="11" />
      <line x1="9" y1="14" x2="15" y2="14" />
      <line x1="9" y1="17" x2="13" y2="17" />
    </g>

    <!-- Settings: two toggle/slider rows -->
    <g v-else-if="illo === 'settings'">
      <line x1="4" y1="8" x2="20" y2="8" stroke-opacity="0.4" />
      <line x1="4" y1="16" x2="20" y2="16" stroke-opacity="0.4" />
      <circle cx="9" cy="8" r="2.5" fill="currentColor" stroke="none" />
      <circle cx="15" cy="16" r="2.5" fill="currentColor" stroke="none" />
    </g>

    <!-- Menu tree: a parent button with two nested child buttons -->
    <g v-else-if="illo === 'menu'">
      <rect x="3" y="3" width="9" height="5" rx="1" />
      <rect x="11" y="11" width="10" height="4" rx="1" />
      <rect x="11" y="17" width="10" height="4" rx="1" />
      <path d="M7 8 v9 h4 M7 13 h4" stroke-opacity="0.7" />
    </g>

    <!-- Theme: a paint palette with two color wells -->
    <g v-else-if="illo === 'theme'">
      <path d="M12 3 a9 9 0 1 0 0 18 a2 2 0 0 0 0 -4 a2 2 0 0 1 0 -4 h2 a5 5 0 0 0 -2 -10 Z" />
      <circle cx="8" cy="9" r="1" fill="currentColor" stroke="none" />
      <circle cx="13" cy="7" r="1" fill="currentColor" stroke="none" />
    </g>

    <!-- Kiosk: a browser window taking over the screen (URL bar + content) -->
    <g v-else>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <circle cx="6" cy="6.5" r="0.6" fill="currentColor" stroke="none" />
      <circle cx="8.5" cy="6.5" r="0.6" fill="currentColor" stroke="none" />
      <path d="M9 14.5 l3 -2.5 l3 2.5" />
    </g>
  </svg>
</template>
