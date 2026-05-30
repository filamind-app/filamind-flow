<script setup lang="ts">
import { computed } from 'vue'

import type { WidgetDefinition } from '@/core/registry'

const props = defineProps<{ widget: WidgetDefinition }>()

const spanClass = computed(() => {
  const spans: Record<number, string> = {
    1: 'sm:col-span-1',
    2: 'sm:col-span-2',
    3: 'sm:col-span-2 xl:col-span-3',
    4: 'sm:col-span-2 xl:col-span-4',
  }
  return spans[props.widget.defaultSize?.w ?? 1] ?? 'sm:col-span-1'
})
</script>

<template>
  <article class="nb-card flex flex-col" :class="spanClass">
    <header class="flex items-center justify-between border-b-3 border-ink px-3 py-2">
      <h2 class="font-display text-sm font-bold uppercase tracking-wide">{{ widget.title }}</h2>
    </header>
    <div class="p-3">
      <component :is="widget.component" />
    </div>
  </article>
</template>
