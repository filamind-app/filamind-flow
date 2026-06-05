<script setup lang="ts" generic="T extends string">
/** The house navigation primitive (#112): a persistent top tab strip, one view at a time.
 *  Replaces three bespoke per-widget strips so navigation looks and behaves identically.
 *  Generic over the tab-id union so `v-model` stays type-safe. Pair with `v-show` in the
 *  parent so an in-progress view (e.g. a wizard) survives a tab switch.
 */
defineProps<{ modelValue: T; tabs: { id: T; label: string }[] }>()
defineEmits<{ 'update:modelValue': [id: T] }>()
</script>

<template>
  <div class="flex flex-wrap gap-1" role="tablist" aria-label="Views">
    <button
      v-for="t in tabs"
      :key="t.id"
      type="button"
      role="tab"
      :aria-selected="modelValue === t.id"
      class="nb-btn px-3 py-1 text-xs"
      :class="modelValue === t.id ? 'bg-brand-cyan ring-2 ring-ink' : 'bg-surface'"
      @click="$emit('update:modelValue', t.id)"
    >
      {{ t.label }}
    </button>
  </div>
</template>
