<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ConnectionStatus from '@/components/system/ConnectionStatus.vue'
import LanguageSelect from '@/components/layout/LanguageSelect.vue'
import ThemeSelect from '@/components/ui/ThemeSelect.vue'
import { useNav } from '@/core/nav'
import { refreshGuard, usePrinterGuard } from '@/core/printerGuard'
import { usePolling } from '@/core/usePolling'

const { t, te } = useI18n({ useScope: 'global' })
const { sidebarOpen } = useNav()

const title = import.meta.env.VITE_APP_TITLE || 'FilaMind Flow'

// Mainsail is served on the same host (default port 80); override with VITE_MAINSAIL_URL.
const mainsailUrl =
  import.meta.env.VITE_MAINSAIL_URL || `${window.location.protocol}//${window.location.hostname}/`

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
        class="nb-btn shrink-0 bg-brand-cyan px-3 py-1.5"
        :href="mainsailUrl"
        :title="t('shell.mainsail.title')"
      >
        <span aria-hidden="true">←</span>
        <span class="hidden sm:inline">{{ t('shell.mainsail.label') }}</span>
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
      <ThemeSelect />
      <!-- Renders only once a second locale's catalog exists (hidden in the en-only build). -->
      <LanguageSelect />
      <ConnectionStatus />
    </div>
  </header>
</template>
