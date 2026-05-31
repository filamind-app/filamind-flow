<script setup lang="ts">
import { computed, onMounted } from 'vue'

import WidgetFrame from '@/components/dashboard/WidgetFrame.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useNav } from '@/core/nav'
import { widgetRegistry } from '@/core/registry'
import { usePrinterStore } from '@/core/store/printer'

const printer = usePrinterStore()
const { current } = useNav()

// A widget id selected in the sidebar → that widget's page; otherwise the
// (currently empty) dashboard home.
const widget = computed(() => widgetRegistry.get(current.value))

onMounted(() => {
  printer.init()
})
</script>

<template>
  <div class="flex min-h-screen bg-paper text-ink">
    <AppSidebar />
    <div class="flex min-w-0 flex-1 flex-col">
      <AppHeader />
      <main class="flex-1 p-4 sm:p-6">
        <section v-if="widget" class="grid grid-cols-1">
          <WidgetFrame :widget="widget" />
        </section>
        <div v-else class="nb-card mx-auto max-w-xl bg-surface p-8 text-center">
          <p class="font-mono text-5xl" aria-hidden="true">▦</p>
          <h2 class="mt-4 font-display text-2xl font-bold">Dashboard</h2>
          <p class="mt-2 text-sm">
            Your panels live in the sidebar — pick one to get started. This home is intentionally
            empty for now.
          </p>
        </div>
      </main>
    </div>
  </div>
</template>
