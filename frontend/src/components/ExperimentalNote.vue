<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/**
 * The honest "this is still being built" banner for the parts of FilaMind that are under active
 * development and research - FilaMind 3d, FilaMind screen, and the widgets that FilaMind 3d
 * unlocks. Rendered wherever those surface so an operator always knows they are looking at a
 * preview that will keep changing, and is invited to suggest improvements.
 */
const { t } = useI18n()
</script>

<template>
  <p
    class="flex items-start gap-2 rounded-brutal border-2 border-ink bg-brand-yellow/25 px-2 py-1 text-[11px]"
    role="note"
  >
    <span aria-hidden="true">🧪</span>
    <span
      ><b>{{ t('common.experimental') }}</b> — {{ t('common.experimentalNote') }}</span
    >
  </p>
</template>
