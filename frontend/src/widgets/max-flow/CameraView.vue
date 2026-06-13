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
    /** Render as a fixed, compact picture-in-picture pinned to the corner. */
    pip?: boolean
  }>(),
  { name: undefined, active: true, intervalMs: 700, pip: false },
)

const { t } = useI18n({ useScope: 'global' })

const tick = ref(0)
const failed = ref(false)
const collapsed = ref(false)
const large = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const src = computed(() => snapshotUrl(props.name, tick.value))
const widthClass = computed(() =>
  !props.pip ? '' : large.value ? 'w-[clamp(280px,42vw,460px)]' : 'w-[clamp(190px,26vw,270px)]',
)

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

// Poll only while active AND expanded — no point fetching snapshots behind a collapsed PiP.
watch(
  [() => props.active, collapsed],
  ([on, isCollapsed]) => {
    if (on && !isCollapsed) {
      failed.value = false
      start()
    } else {
      stop()
    }
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
  <div
    class="nb-card overflow-hidden bg-paper p-0"
    :class="
      pip ? ['fixed bottom-3 end-3 z-40 shadow-[4px_4px_0_0_var(--color-ink)]', widthClass] : ''
    "
    :role="pip ? 'complementary' : undefined"
    :aria-label="pip ? t('maxFlow.camera.title') : undefined"
  >
    <div class="flex items-center justify-between gap-2 border-b-2 border-ink bg-surface px-2 py-1">
      <span class="truncate text-[11px] font-bold">📷 {{ t('maxFlow.camera.title') }}</span>
      <div class="flex shrink-0 items-center gap-1.5">
        <span
          v-if="active && !failed"
          class="flex items-center gap-1 font-mono text-[10px] text-brand-red"
        >
          <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-brand-red"></span>
          {{ t('maxFlow.camera.live') }}
        </span>
        <template v-if="pip">
          <button
            type="button"
            class="rounded border border-ink px-1 text-[10px] leading-none hover:bg-paper"
            :title="large ? t('maxFlow.camera.shrink') : t('maxFlow.camera.enlarge')"
            :aria-label="large ? t('maxFlow.camera.shrink') : t('maxFlow.camera.enlarge')"
            @click="large = !large"
          >
            {{ large ? '▢' : '▣' }}
          </button>
          <button
            type="button"
            class="rounded border border-ink px-1 text-[10px] leading-none hover:bg-paper"
            :title="collapsed ? t('maxFlow.camera.maximize') : t('maxFlow.camera.minimize')"
            :aria-label="collapsed ? t('maxFlow.camera.maximize') : t('maxFlow.camera.minimize')"
            @click="collapsed = !collapsed"
          >
            {{ collapsed ? '▸' : '▾' }}
          </button>
        </template>
      </div>
    </div>
    <div
      v-show="!collapsed"
      data-testid="cam-feed"
      class="relative bg-ink/90"
      style="aspect-ratio: 16 / 9"
    >
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
