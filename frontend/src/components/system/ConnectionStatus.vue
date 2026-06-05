<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { usePrinterStore } from '@/core/store/printer'

const { t } = useI18n({ useScope: 'global' })
const { connectionState } = storeToRefs(usePrinterStore())

const meta = computed(() => {
  switch (connectionState.value) {
    case 'connected':
      return { label: t('shell.connection.connected'), class: 'bg-brand-lime' }
    case 'connecting':
    case 'reconnecting':
      return { label: t('shell.connection.connecting'), class: 'bg-brand-yellow' }
    case 'error':
      return { label: t('shell.connection.error'), class: 'bg-brand-red text-surface' }
    case 'closed':
      return { label: t('shell.connection.offline'), class: 'bg-ink text-surface' }
    default:
      return { label: t('shell.connection.idle'), class: 'bg-surface' }
  }
})
</script>

<template>
  <span class="nb-badge" :class="meta.class">
    <span class="inline-block h-2 w-2 rounded-full bg-ink" aria-hidden="true"></span>
    {{ meta.label }}
  </span>
</template>
