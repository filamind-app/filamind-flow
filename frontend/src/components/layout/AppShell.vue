<script setup lang="ts">
import { computed, onMounted } from 'vue'

import DashboardHome from '@/components/dashboard/DashboardHome.vue'
import WidgetFrame from '@/components/dashboard/WidgetFrame.vue'
import ReportDialog from '@/components/feedback/ReportDialog.vue'
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
        <DashboardHome v-else />
      </main>
    </div>
    <!-- Mounted once: the shared bug/feature report dialog, opened from the header menu or any
         "Report this error" button. -->
    <ReportDialog />
  </div>
</template>
