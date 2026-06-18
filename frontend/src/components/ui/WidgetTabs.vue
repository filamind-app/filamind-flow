<script setup lang="ts" generic="T extends string">
/** The house navigation primitive (#112): a persistent top tab strip, one view at a time.
 *  Replaces three bespoke per-widget strips so navigation looks and behaves identically.
 *  Generic over the tab-id union so `v-model` stays type-safe. Pair with `v-show` in the
 *  parent so an in-progress view (e.g. a wizard) survives a tab switch.
 */
import { useI18n } from 'vue-i18n'

defineProps<{ modelValue: T; tabs: { id: T; label: string }[] }>()
defineEmits<{ 'update:modelValue': [id: T] }>()

const { t } = useI18n({ useScope: 'global' })
</script>

<template>
  <div class="flex flex-wrap gap-1" role="tablist" :aria-label="t('widgetTabs.views')">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      role="tab"
      :aria-selected="modelValue === tab.id"
      class="nb-btn px-3 py-1 text-xs"
      :class="modelValue === tab.id ? 'bg-brand-cyan ring-2 ring-ink' : 'bg-surface'"
      @click="$emit('update:modelValue', tab.id)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>
