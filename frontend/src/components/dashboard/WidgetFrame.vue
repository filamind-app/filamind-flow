<script setup lang="ts">
import { widgetTitle } from '@/core/i18n'
import type { WidgetDefinition } from '@/core/registry'

defineProps<{ widget: WidgetDefinition }>()
</script>

<template>
  <article class="nb-card flex flex-col">
    <header class="flex items-center justify-between border-b-3 border-ink px-3 py-2">
      <h2 class="font-display text-sm font-bold uppercase tracking-wide">
        {{ widgetTitle(widget) }}
      </h2>
    </header>
    <div class="p-3">
      <component :is="widget.component" />
    </div>
  </article>
</template>
