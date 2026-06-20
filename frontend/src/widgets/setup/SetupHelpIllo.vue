<script setup lang="ts">
/** Generic help illustration for the Setup widget (HelpDrawer requires an `illo` component).
 *  The Setup guide uses no per-topic art, so this renders a single neutral glyph. */
defineProps<{ illo?: string }>()
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="2" />
    <path d="M8 12h8M8 8h8M8 16h5" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
  </svg>
</template>
