<script setup lang="ts">
import ConnectionStatus from '@/components/system/ConnectionStatus.vue'

const title = import.meta.env.VITE_APP_TITLE || 'FilaMind Flow'
</script>

<template>
  <header
    class="flex items-center justify-between gap-4 border-b-3 border-ink bg-surface px-4 py-3 sm:px-6"
  >
    <h1 class="font-display text-xl font-bold sm:text-2xl">{{ title }}</h1>
    <ConnectionStatus />
  </header>
</template>
