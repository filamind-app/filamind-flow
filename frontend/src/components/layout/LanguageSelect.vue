<script setup lang="ts">
/** Language switcher (i18n Phase 0). Reuses the shared ComboSelect primitive so it matches every
 *  other picker. Renders nothing until more than one locale has a catalog — so the Phase-0 (en-only)
 *  build shows no new chrome; each added `src/locales/<code>/` folder makes it appear automatically. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import { availableLocales, setLocale } from '@/core/i18n'

const { t, locale } = useI18n({ useScope: 'global' })

const options = computed(() => availableLocales.map((m) => ({ value: m.code, label: m.label })))

function onChange(code: string | null): void {
  if (code) void setLocale(code)
}
</script>

<template>
  <ComboSelect
    v-if="availableLocales.length > 1"
    :model-value="locale"
    :options="options"
    :placeholder="t('shell.language.select')"
    @update:model-value="onChange"
  />
</template>
