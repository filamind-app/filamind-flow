<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useNav } from '@/core/nav'

const { t } = useI18n()
const { go } = useNav()

/** FilaMind flow's checks & tests, as big touch targets. Labels reuse the shared widget titles
 *  (shell.widgets.<id>.title), so they're already translated in every locale. */
const TOOLS: { id: string; icon: string }[] = [
  { id: 'preflight', icon: '🚦' },
  { id: 'machine-doctor', icon: '🩺' },
  { id: 'input-shaping', icon: '📈' },
  { id: 'tuning', icon: '🎚' },
  { id: 'max-flow', icon: '🌡' },
]
</script>

<template>
  <section class="nb-card flex flex-col gap-3 p-3">
    <h3 class="font-display text-sm font-bold">{{ t('klipperscreenStudio.touchPanel.title') }}</h3>
    <p class="text-sm text-ink/70">{{ t('klipperscreenStudio.touchPanel.intro') }}</p>
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <button
        v-for="tool in TOOLS"
        :key="tool.id"
        class="nb-btn flex min-h-20 flex-col items-center justify-center gap-1 p-4 text-center"
        @click="go(tool.id)"
      >
        <span class="text-3xl" aria-hidden="true">{{ tool.icon }}</span>
        <span class="text-sm font-bold">{{ t(`shell.widgets.${tool.id}.title`) }}</span>
      </button>
    </div>
  </section>
</template>
