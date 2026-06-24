<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchTouchStatus, switchTouch, type TouchKey, type TouchStatus } from './api'

const { t } = useI18n()

const status = ref<TouchStatus | null>(null)
const persist = ref(true)
const busy = ref<TouchKey | null>(null)
const error = ref<string | null>(null)

const KEYS: TouchKey[] = ['klipperscreen', 'guppyscreen', 'filamind-screen', 'filamind-flow']
const LABELS: Record<TouchKey, string> = {
  klipperscreen: 'KlipperScreen',
  guppyscreen: 'Guppyscreen',
  'filamind-screen': 'FilaMind screen',
  'filamind-flow': 'FilaMind flow',
}

async function load(): Promise<void> {
  error.value = null
  try {
    status.value = await fetchTouchStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function pick(k: TouchKey): Promise<void> {
  if (busy.value) return
  busy.value = k
  error.value = null
  try {
    status.value = await switchTouch(k, persist.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}

onMounted(load)
</script>

<template>
  <section class="nb-card flex flex-col gap-3 p-3">
    <header class="flex items-center justify-between gap-2">
      <h3 class="font-display text-sm font-bold">{{ t('klipperscreenStudio.selector.title') }}</h3>
      <button class="nb-btn px-3 py-1 text-xs" @click="load">
        {{ t('klipperscreenStudio.selector.refresh') }}
      </button>
    </header>
    <p class="text-sm text-ink/70">{{ t('klipperscreenStudio.selector.intro') }}</p>

    <ul class="flex flex-col gap-2">
      <li
        v-for="k in KEYS"
        :key="k"
        class="nb-card flex flex-wrap items-center gap-2 bg-surface p-2"
      >
        <span class="font-bold">{{ LABELS[k] }}</span>
        <span v-if="status?.screens[k]?.active" class="nb-badge bg-brand-green text-xs">
          {{ t('klipperscreenStudio.selector.active') }}
        </span>
        <span v-else-if="status?.screens[k]?.enabled" class="nb-badge bg-brand-cyan text-xs">
          {{ t('klipperscreenStudio.selector.boot') }}
        </span>
        <span class="ms-auto flex items-center gap-2">
          <span
            v-if="!status?.screens[k]?.installed"
            class="nb-badge bg-surface text-xs text-ink/60"
          >
            {{ t('klipperscreenStudio.selector.notInstalled') }}
          </span>
          <span
            v-else-if="status?.screens[k]?.manageable === false"
            class="nb-badge bg-surface text-xs text-ink/60"
            :title="t('klipperscreenStudio.selector.notManageableHint')"
          >
            {{ t('klipperscreenStudio.selector.installedNotManageable') }}
          </span>
          <button
            v-else-if="!status?.screens[k]?.active"
            class="nb-btn px-3 py-1 text-sm"
            :disabled="busy !== null"
            @click="pick(k)"
          >
            {{
              busy === k
                ? t('klipperscreenStudio.selector.switching')
                : t('klipperscreenStudio.selector.use')
            }}
          </button>
        </span>
      </li>
    </ul>

    <label class="flex items-center gap-2 text-sm">
      <input v-model="persist" type="checkbox" />
      {{ t('klipperscreenStudio.selector.persist') }}
    </label>

    <p v-if="error" class="nb-card bg-brand-red/20 p-2 text-sm" role="alert">{{ error }}</p>
  </section>
</template>
