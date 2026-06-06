<script setup lang="ts">
/** Live driver monitor (P6, read-only). When open, polls the driver's live telemetry
 *  every ~1.5s and shows temperature, StallGuard load (SG_RESULT) with a sparkline,
 *  current scale (CS_ACTUAL), and any fault flags. drv_status is only populated while the
 *  motor is enabled, so an idle motor shows a hint instead. No writes, no motion.
 */
import { computed, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchDriverLive } from './api'
import { activeFlags, drvNum, sparklinePath } from './format'
import type { DriverLive, TmcDriver } from './types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{ driver: TmcDriver }>()

const open = ref(false)
const live = ref<DriverLive | null>(null)
const sgHistory = ref<number[]>([])
let timer: ReturnType<typeof setInterval> | null = null

async function poll(): Promise<void> {
  try {
    const data = await fetchDriverLive(props.driver.stepper)
    live.value = data
    const sg = drvNum(data.drv_status, 'sg_result')
    if (sg !== null) sgHistory.value = [...sgHistory.value.slice(-39), sg]
  } catch {
    /* transient poll failure — keep the last sample */
  }
}

function toggle(): void {
  open.value = !open.value
  if (open.value) {
    sgHistory.value = []
    void poll()
    timer = setInterval(() => void poll(), 1500)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const drv = computed(() => live.value?.drv_status ?? null)
const sg = computed(() => drvNum(drv.value, 'sg_result'))
const cs = computed(() => drvNum(drv.value, 'cs_actual'))
const flags = computed(() => activeFlags(drv.value))
const spark = computed(() => sparklinePath(sgHistory.value, 100, 22))
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="flex w-full items-center gap-1.5 text-start opacity-70 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="toggle"
    >
      <span aria-hidden="true">{{ open ? '▾' : '▸' }}</span>
      <span aria-hidden="true">📈</span>
      <span class="font-bold">{{ t('motorDrivers.liveMonitor.toggle') }}</span>
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-1 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <template v-if="drv">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <span v-if="live?.temperature != null">{{
            t('motorDrivers.liveMonitor.temp', { temp: live.temperature.toFixed(1) })
          }}</span>
          <span v-if="sg != null">{{ t('motorDrivers.liveMonitor.sg', { sg }) }}</span>
          <span v-if="cs != null">{{ t('motorDrivers.liveMonitor.cs', { cs }) }}</span>
          <span class="opacity-50">{{ t('motorDrivers.liveMonitor.updates') }}</span>
        </div>
        <svg
          v-if="spark"
          viewBox="0 0 100 22"
          preserveAspectRatio="none"
          class="h-6 w-full"
          aria-hidden="true"
        >
          <path :d="spark" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
        <div v-if="flags.length" class="flex flex-wrap gap-1">
          <span
            v-for="f in flags"
            :key="f"
            class="nb-badge bg-brand-red px-1.5 py-0 text-[9px] text-surface"
            >{{ f }}</span
          >
        </div>
        <div v-else class="opacity-60">{{ t('motorDrivers.liveMonitor.noFaults') }}</div>
      </template>
      <p v-else class="opacity-70">
        {{ t('motorDrivers.liveMonitor.idle') }}
      </p>
    </div>
  </div>
</template>
