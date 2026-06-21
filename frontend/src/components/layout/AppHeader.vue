<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import FeedbackMenu from '@/components/feedback/FeedbackMenu.vue'
import LanguageMenu from '@/components/layout/LanguageMenu.vue'
import ThemeMenu from '@/components/layout/ThemeMenu.vue'
import ConnectionStatus from '@/components/system/ConnectionStatus.vue'
import { useNav } from '@/core/nav'
import { showMainsailLink, detectBackUi, type BackUi } from '@/core/host/adapter'
import { refreshGuard, usePrinterGuard } from '@/core/printerGuard'
import { usePolling } from '@/core/usePolling'

const { t, te } = useI18n({ useScope: 'global' })
const { sidebarOpen } = useNav()

const title = import.meta.env.VITE_APP_TITLE || 'FilaMind Flow'

// The "back to the host UI" link only applies to the Mainsail-hosted build (hidden under the suite host).
// The host UI is served on the same origin (override with VITE_MAINSAIL_URL); detectBackUi() then
// probes whether it's Mainsail or Fluidd so the label is right for either (best-effort, never throws).
const backVisible = showMainsailLink()
const backUi = ref<BackUi>({
  name: '',
  url:
    import.meta.env.VITE_MAINSAIL_URL ||
    `${window.location.protocol}//${window.location.hostname}/`,
})
const backLabel = computed(() => backUi.value.name || t('shell.backUi.label'))
onMounted(async () => {
  if (backVisible)
    backUi.value = await detectBackUi({ url: import.meta.env.VITE_MAINSAIL_URL || undefined })
})

// Global write-lock awareness: one shell-level poll feeds the whole app (and this badge), so the
// user learns the printer is busy BEFORE a gated action refuses them.
const guard = usePrinterGuard()
usePolling(refreshGuard, 5000)

const guardBadge = computed<{ text: string; printing: boolean } | null>(() => {
  if (!guard.reachable) return null
  if (guard.printState === 'printing' || guard.printState === 'paused') {
    return { text: t('shell.guard.printing'), printing: true }
  }
  if (guard.locked && guard.operation) {
    const key = `shell.guard.op.${guard.operation}`
    const op = te(key) ? t(key) : guard.operation
    return { text: t('shell.guard.running', { op }), printing: false }
  }
  return null
})
</script>

<template>
  <header
    class="flex items-center justify-between gap-4 border-b-3 border-ink bg-surface px-4 py-3 sm:px-6"
  >
    <div class="flex min-w-0 items-center gap-3">
      <button
        class="nb-btn shrink-0 px-2 py-1.5 md:hidden"
        :aria-label="t('shell.nav.toggle')"
        :aria-expanded="sidebarOpen"
        @click="sidebarOpen = !sidebarOpen"
      >
        <span aria-hidden="true">☰</span>
      </button>
      <a
        v-if="backVisible"
        class="nb-btn shrink-0 bg-brand-cyan px-3 py-1.5"
        :href="backUi.url"
        :title="t('shell.backUi.title')"
      >
        <span aria-hidden="true">←</span>
        <span class="hidden sm:inline">{{ backLabel }}</span>
      </a>
      <h1 class="truncate font-display text-xl font-bold sm:text-2xl">{{ title }}</h1>
      <span
        v-if="guardBadge"
        class="nb-card hidden shrink-0 px-2 py-1 text-xs font-bold sm:inline-block"
        :class="guardBadge.printing ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'"
        role="status"
      >
        <span aria-hidden="true">{{ guardBadge.printing ? '🖨' : '⚙' }}</span>
        {{ guardBadge.text }}
      </span>
    </div>
    <div class="flex shrink-0 items-center gap-2">
      <ThemeMenu />
      <!-- Renders only once a second locale's catalog exists (hidden in the en-only build). -->
      <LanguageMenu />
      <FeedbackMenu />
      <ConnectionStatus />
    </div>
  </header>
</template>
