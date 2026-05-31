<script setup lang="ts">
import { computed } from 'vue'

import { useNav } from '@/core/nav'
import { widgetRegistry } from '@/core/registry'

const { current, go } = useNav()

// Dashboard (the empty home) plus one entry per registered widget — each widget
// gets its own page, reached from here.
const items = computed(() => [
  { id: 'dashboard', label: 'Dashboard', icon: '▣' },
  ...widgetRegistry.all().map((w) => ({ id: w.id, label: w.title, icon: '◳' })),
])
</script>

<template>
  <aside
    class="hidden w-60 shrink-0 flex-col gap-6 border-r-3 border-ink bg-brand-yellow p-4 md:flex"
  >
    <div class="nb-card bg-surface px-3 py-4">
      <p class="font-display text-2xl font-bold leading-none">FilaMind</p>
      <p class="font-mono text-xs tracking-tight">FLOW · klipper panel</p>
    </div>

    <nav class="flex flex-col gap-2">
      <button
        v-for="item in items"
        :key="item.id"
        class="nb-btn justify-start text-left"
        :class="current === item.id ? 'bg-brand-cyan' : 'bg-surface'"
        @click="go(item.id)"
      >
        <span aria-hidden="true">{{ item.icon }}</span>
        {{ item.label }}
      </button>
    </nav>

    <p class="mt-auto font-mono text-[10px] leading-tight opacity-70">
      Moonraker · Klipper<br />by DeltaFabs team
    </p>
  </aside>
</template>
