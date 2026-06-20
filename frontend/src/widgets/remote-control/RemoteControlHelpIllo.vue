<script setup lang="ts">
/** Generic help illustration for the Remote Control widget (HelpDrawer requires an `illo`).
 *  A small touchscreen with a signal arc — "steer the screen from here". */
defineProps<{ illo?: string }>()
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="4" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="2" />
    <path d="M9 20h6M12 16v4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
    <path
      d="M14 8a3 3 0 0 1 0 4M16 6.5a5 5 0 0 1 0 7"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
    />
  </svg>
</template>
