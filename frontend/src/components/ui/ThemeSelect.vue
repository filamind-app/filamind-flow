<script setup lang="ts">
/** Theme switcher. Mirrors LanguageSelect.vue — reuses the shared ComboSelect primitive so it
 *  matches every other picker. Options are the available themes with translated labels; selecting
 *  one calls setTheme(), which writes <html data-theme> (recoloring every token-driven utility),
 *  persists the choice, and updates the reactive currentTheme ref. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import { availableThemes, currentTheme, setTheme, type ThemeKey } from '@/core/theme'

const { t } = useI18n({ useScope: 'global' })

const options = computed(() => availableThemes.map((m) => ({ value: m.key, label: t(m.labelKey) })))

function onChange(key: string | null): void {
  if (key) setTheme(key as ThemeKey)
}
</script>

<template>
  <ComboSelect
    :model-value="currentTheme"
    :options="options"
    :placeholder="t('theme.label')"
    @update:model-value="onChange"
  />
</template>
