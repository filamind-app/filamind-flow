<script setup lang="ts">
/** Host Control · Boot - the host's boot configuration: the systemd default target, whether it
 *  boots graphical, the plymouth theme, a preview of the active boot splash, and a splash design
 *  studio to change it (gated write). */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { bootSplashUrl, fetchBootInfo } from './api'
import SplashStudio from './SplashStudio.vue'
import type { BootInfo } from './types'

const { t } = useI18n({ useScope: 'global' })

const info = ref<BootInfo | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const splashFailed = ref(false)
const showStudio = ref(false)

function onApplied(): void {
  showStudio.value = false
  void load()
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  splashFailed.value = false
  try {
    info.value = await fetchBootInfo()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const splashSrc = computed(() => (info.value?.splash ? bootSplashUrl() : ''))
const kb = (n: number): string => `${Math.round(n / 1024)} KB`
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="min-w-0 flex-1 text-[11px] opacity-70">{{ t('hostControl.boot.intro') }}</p>
      <button type="button" class="nb-btn text-xs" :disabled="loading" @click="load">
        ↻ {{ t('hostControl.boot.refresh') }}
      </button>
    </div>

    <p v-if="loading" class="font-mono text-xs opacity-70">{{ t('hostControl.boot.loading') }}</p>
    <p v-else-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>

    <template v-else-if="info">
      <dl
        class="nb-card grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 bg-surface p-3 font-mono text-xs"
      >
        <dt class="opacity-60">{{ t('hostControl.boot.defaultTarget') }}</dt>
        <dd>
          {{ info.default_target || '-' }}
          <span
            v-if="info.default_target"
            class="nb-badge ms-1 text-[10px]"
            :class="info.graphical ? 'bg-brand-cyan' : 'bg-surface'"
          >
            {{ t(info.graphical ? 'hostControl.boot.graphical' : 'hostControl.boot.console') }}
          </span>
        </dd>
        <dt class="opacity-60">{{ t('hostControl.boot.plymouth') }}</dt>
        <dd>{{ info.plymouth_theme || t('hostControl.boot.none') }}</dd>
      </dl>

      <div class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold">{{ t('hostControl.boot.splash') }}</p>
        <template v-if="info.splash && !splashFailed">
          <img
            :src="splashSrc"
            :alt="t('hostControl.boot.splash')"
            class="max-h-56 w-full rounded-brutal border-2 border-ink bg-ink/5 object-contain"
            @error="splashFailed = true"
          />
          <p class="font-mono text-[11px] opacity-60">
            {{ info.splash.path }} · {{ kb(info.splash.size) }}
          </p>
        </template>
        <p v-else class="font-mono text-[11px] opacity-60">{{ t('hostControl.boot.noSplash') }}</p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <button class="nb-btn text-xs" @click="showStudio = !showStudio">
          🎨
          {{ showStudio ? t('hostControl.boot.studio.close') : t('hostControl.boot.studio.open') }}
        </button>
      </div>
      <SplashStudio v-if="showStudio" @applied="onApplied" />
    </template>
  </div>
</template>
