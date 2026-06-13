<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { snapshotUrl } from './camera'

const props = withDefaults(
  defineProps<{
    /** Camera name (omit for the default). */
    name?: string
    /** Poll + show the live feed while true; pause when false. */
    active?: boolean
    /** Snapshot refresh interval (ms). */
    intervalMs?: number
  }>(),
  { name: undefined, active: true, intervalMs: 700 },
)

const { t } = useI18n({ useScope: 'global' })

const tick = ref(0)
const failed = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const src = computed(() => snapshotUrl(props.name, tick.value))

function stop(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

function start(): void {
  stop()
  tick.value += 1 // immediate first frame
  timer = setInterval(
    () => {
      tick.value += 1
    },
    Math.max(200, props.intervalMs),
  )
}

watch(
  () => props.active,
  (on) => {
    failed.value = false
    if (on) start()
    else stop()
  },
  { immediate: true },
)

onBeforeUnmount(stop)

function onError(): void {
  failed.value = true
}
function onLoad(): void {
  failed.value = false
}
</script>

<template>
  <div class="nb-card overflow-hidden bg-paper p-0">
    <div class="flex items-center justify-between border-b-2 border-ink bg-surface px-2 py-1">
      <span class="text-[11px] font-bold">📷 {{ t('maxFlow.camera.title') }}</span>
      <span
        v-if="active && !failed"
        class="flex items-center gap-1 font-mono text-[10px] text-brand-red"
      >
        <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-brand-red"></span>
        {{ t('maxFlow.camera.live') }}
      </span>
    </div>
    <div class="relative bg-ink/90" style="aspect-ratio: 16 / 9">
      <img
        v-show="!failed"
        :src="src"
        :alt="t('maxFlow.camera.title')"
        class="h-full w-full object-contain"
        @error="onError"
        @load="onLoad"
      />
      <div
        v-if="failed"
        class="absolute inset-0 flex items-center justify-center p-2 text-center text-[11px] text-paper opacity-80"
      >
        {{ t('maxFlow.camera.error') }}
      </div>
    </div>
  </div>
</template>
