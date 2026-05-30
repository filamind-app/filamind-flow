<script setup lang="ts">
import { onMounted } from 'vue'

import DashboardGrid from '@/components/dashboard/DashboardGrid.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { usePrinterStore } from '@/core/store/printer'

const printer = usePrinterStore()

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
        <DashboardGrid />
      </main>
    </div>
  </div>
</template>
