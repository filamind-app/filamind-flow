<script setup lang="ts">
// Small hand-drawn-ish glyphs for the Control help drawer (one per topic). Kept tiny and
// currentColor-based so it inherits the theme ink.
defineProps<{ illo: string }>()
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
    <template v-if="illo === 'job'">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 12 L12 7 M12 12 L16 14" stroke-linecap="round" />
    </template>
    <template v-else-if="illo === 'temps'">
      <path d="M10 4 a2 2 0 0 1 4 0 v9 a4 4 0 1 1 -4 0 z" stroke-linejoin="round" />
      <circle cx="12" cy="17" r="2" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="illo === 'motion'">
      <path
        d="M12 3 v18 M3 12 h18 M12 3 l-3 3 M12 3 l3 3 M12 21 l-3 -3 M12 21 l3 -3"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </template>
    <template v-else>
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <circle cx="12" cy="12" r="3" />
    </template>
  </svg>
</template>
