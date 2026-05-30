<script setup lang="ts">
import { computed } from 'vue'

import EmptyState from '@/components/dashboard/EmptyState.vue'
import WidgetFrame from '@/components/dashboard/WidgetFrame.vue'
import { widgetRegistry } from '@/core/registry'

// Widgets register at startup (before mount), so a one-shot read is sufficient
// for the scaffold. Runtime (de)registration would need a reactive registry.
const widgets = computed(() => widgetRegistry.all())
</script>

<template>
  <section v-if="widgets.length" class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
    <WidgetFrame v-for="widget in widgets" :key="widget.id" :widget="widget" />
  </section>
  <EmptyState v-else />
</template>
