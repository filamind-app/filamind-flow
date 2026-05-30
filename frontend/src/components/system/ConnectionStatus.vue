<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import { usePrinterStore } from '@/core/store/printer'

const { connectionState } = storeToRefs(usePrinterStore())

const meta = computed(() => {
  switch (connectionState.value) {
    case 'connected':
      return { label: 'Connected', class: 'bg-brand-lime' }
    case 'connecting':
    case 'reconnecting':
      return { label: 'Connecting', class: 'bg-brand-yellow' }
    case 'error':
      return { label: 'Error', class: 'bg-brand-red text-surface' }
    case 'closed':
      return { label: 'Offline', class: 'bg-ink text-surface' }
    default:
      return { label: 'Idle', class: 'bg-surface' }
  }
})
</script>

<template>
  <span class="nb-badge" :class="meta.class">
    <span class="inline-block h-2 w-2 rounded-full bg-ink" aria-hidden="true"></span>
    {{ meta.label }}
  </span>
</template>
