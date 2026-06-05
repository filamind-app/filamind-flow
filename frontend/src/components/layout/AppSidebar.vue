<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { widgetTitle } from '@/core/i18n'
import { useNav } from '@/core/nav'
import { widgetRegistry } from '@/core/registry'

const { t } = useI18n({ useScope: 'global' })
const { current, go, sidebarOpen } = useNav()

// Dashboard (the empty home) plus one entry per registered widget — each widget
// gets its own page, reached from here. Icons come from each widget's definition.
const items = computed(() => [
  { id: 'dashboard', label: t('shell.nav.dashboard'), icon: '▣' },
  ...widgetRegistry.all().map((w) => ({ id: w.id, label: widgetTitle(w), icon: w.icon ?? '◳' })),
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
    class="w-60 shrink-0 flex-col gap-6 border-e-3 border-ink bg-brand-yellow p-4 md:static md:z-auto md:flex"
    :class="sidebarOpen ? 'fixed inset-y-0 start-0 z-40 flex' : 'hidden'"
  >
    <div class="nb-card bg-surface px-3 py-4">
      <p class="font-display text-2xl font-bold leading-none">FilaMind</p>
      <p class="font-mono text-xs tracking-tight">{{ t('shell.brand.tagline') }}</p>
    </div>

    <nav class="flex flex-col gap-2">
      <button
        v-for="item in items"
        :key="item.id"
        class="nb-btn w-full justify-start text-start"
        :class="current === item.id ? 'bg-brand-cyan' : 'bg-surface'"
        @click="go(item.id)"
      >
        <span class="w-5 shrink-0 text-center" aria-hidden="true">{{ item.icon }}</span>
        <span class="truncate">{{ item.label }}</span>
      </button>
    </nav>

    <p class="mt-auto font-mono text-[10px] leading-tight opacity-70">
      {{ t('shell.footer.stack') }}<br />{{ t('shell.footer.by') }}
    </p>
  </aside>
</template>
