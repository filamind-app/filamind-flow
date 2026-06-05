<script setup lang="ts">
import { computed } from 'vue'

import { useNav } from '@/core/nav'
import { widgetRegistry } from '@/core/registry'

const { current, go, sidebarOpen } = useNav()

// Dashboard (the empty home) plus one entry per registered widget — each widget
// gets its own page, reached from here. Icons come from each widget's definition.
const items = computed(() => [
  { id: 'dashboard', label: 'Dashboard', icon: '▣' },
  ...widgetRegistry.all().map((w) => ({ id: w.id, label: w.title, icon: w.icon ?? '◳' })),
])
</script>

<template>
  <!-- Backdrop for the off-canvas drawer on narrow screens. -->
  <div
    v-if="sidebarOpen"
    class="fixed inset-0 z-30 bg-ink/50 md:hidden"
    @click="sidebarOpen = false"
  />

  <aside
    class="w-60 shrink-0 flex-col gap-6 border-r-3 border-ink bg-brand-yellow p-4 md:static md:z-auto md:flex"
    :class="sidebarOpen ? 'fixed inset-y-0 left-0 z-40 flex' : 'hidden'"
  >
    <div class="nb-card bg-surface px-3 py-4">
      <p class="font-display text-2xl font-bold leading-none">FilaMind</p>
      <p class="font-mono text-xs tracking-tight">FLOW · klipper panel</p>
    </div>

    <nav class="flex flex-col gap-2">
      <button
        v-for="item in items"
        :key="item.id"
        class="nb-btn w-full justify-start text-left"
        :class="current === item.id ? 'bg-brand-cyan' : 'bg-surface'"
        @click="go(item.id)"
      >
        <span class="w-5 shrink-0 text-center" aria-hidden="true">{{ item.icon }}</span>
        <span class="truncate">{{ item.label }}</span>
      </button>
    </nav>

    <p class="mt-auto font-mono text-[10px] leading-tight opacity-70">
      Moonraker · Klipper<br />by DeltaFabs team
    </p>
  </aside>
</template>
