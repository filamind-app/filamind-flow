<script setup lang="ts">
import ConnectionStatus from '@/components/system/ConnectionStatus.vue'

const title = import.meta.env.VITE_APP_TITLE || 'FilaMind Flow'

// Mainsail is served on the same host (default port 80); override with VITE_MAINSAIL_URL.
const mainsailUrl =
  import.meta.env.VITE_MAINSAIL_URL || `${window.location.protocol}//${window.location.hostname}/`
</script>

<template>
  <header
    class="flex items-center justify-between gap-4 border-b-3 border-ink bg-surface px-4 py-3 sm:px-6"
  >
    <div class="flex min-w-0 items-center gap-3">
      <a
        class="nb-btn shrink-0 bg-brand-cyan px-3 py-1.5"
        :href="mainsailUrl"
        title="Back to Mainsail"
      >
        <span aria-hidden="true">←</span>
        <span class="hidden sm:inline">Mainsail</span>
      </a>
      <h1 class="truncate font-display text-xl font-bold sm:text-2xl">{{ title }}</h1>
    </div>
    <ConnectionStatus />
  </header>
</template>
