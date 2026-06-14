<script setup lang="ts">
/** Flash progress — replaces the raw command window during a flash with a phase progress
 *  bar + a current-step label, surfacing only REAL errors (the `!!` lines) and keeping the
 *  full command output behind a collapsible "details" disclosure for diagnosis. Works for a
 *  single-board flash (phases parsed from the log) and a batch (explicit step/total). */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import LogPane from '@/components/ui/LogPane.vue'

import { parseFlashStatus, stripPhaseMarkers, type FlashPhase } from './flashProgress'

const props = defineProps<{
  log: string
  busy: boolean
  /** Batch only: device counter, shown instead of the parsed single-flash phase. */
  step?: number | null
  total?: number | null
  /** Batch only: name of the device currently flashing (from task progress). */
  detail?: string | null
}>()

const { t, te } = useI18n({ useScope: 'global' })

const status = computed(() => parseFlashStatus(props.log, props.busy))
const isBatch = computed(() => props.total != null && props.total > 0)

const fraction = computed(() => {
  if (isBatch.value) {
    const done = status.value.done ? props.total! : (props.step ?? 0) - (props.busy ? 1 : 0)
    return props.total! > 0 ? Math.max(0, Math.min(1, done / props.total!)) : 0
  }
  return status.value.fraction
})

function phaseLabel(phase: FlashPhase | null): string {
  const key = `firmware.flashProgress.phase.${phase ?? 'start'}`
  return te(key) ? t(key) : t('firmware.flashProgress.phase.start')
}

const headline = computed(() => {
  if (status.value.failed) return t('firmware.flashProgress.failed')
  if (
    status.value.done ||
    (isBatch.value && !props.busy && (props.step ?? 0) >= (props.total ?? 0))
  )
    return t('firmware.flashProgress.done')
  if (isBatch.value)
    return t('firmware.flashProgress.batchStep', {
      step: props.step ?? 0,
      total: props.total ?? 0,
      device: props.detail ?? '',
    })
  return phaseLabel(status.value.phase)
})

const barClass = computed(() =>
  status.value.failed ? 'bg-brand-red' : status.value.done ? 'bg-brand-lime' : 'bg-brand-cyan',
)

const cleanLog = computed(() => stripPhaseMarkers(props.log))
const pct = computed(() => Math.round(fraction.value * 100))
</script>

<template>
  <div class="space-y-1.5" role="status" aria-live="polite">
    <div class="flex items-center justify-between gap-2 text-[11px] font-bold">
      <span class="flex min-w-0 items-center gap-1.5">
        <span
          v-if="busy && !status.failed"
          class="inline-block h-2.5 w-2.5 shrink-0 animate-spin rounded-full border-2 border-ink border-t-transparent"
          aria-hidden="true"
        />
        <span v-else-if="status.done" aria-hidden="true">✓</span>
        <span v-else-if="status.failed" aria-hidden="true">✕</span>
        <span class="truncate">{{ headline }}</span>
      </span>
      <span class="shrink-0 font-mono opacity-70">{{ pct }}%</span>
    </div>

    <!-- Progress track -->
    <div class="h-3 overflow-hidden rounded-brutal border-2 border-ink bg-paper">
      <div
        class="h-full transition-[width] duration-300 ease-out"
        :class="barClass"
        :style="{ width: pct + '%' }"
      />
    </div>

    <!-- Real failures, surfaced plainly (benign command-window noise stays in details). -->
    <div
      v-if="status.errors.length"
      role="alert"
      class="space-y-0.5 rounded-brutal border-2 border-brand-red bg-brand-red/10 p-1.5"
    >
      <p class="text-[11px] font-bold">{{ t('firmware.flashProgress.errorsTitle') }}</p>
      <p
        v-for="(e, i) in status.errors"
        :key="i"
        class="font-mono text-[10px] leading-snug text-brand-red"
      >
        {{ e }}
      </p>
    </div>

    <!-- Full command output, collapsed by default; auto-open on failure for diagnosis. -->
    <details v-if="cleanLog.trim()" :open="status.failed">
      <summary class="cursor-pointer text-[10px] opacity-60">
        {{ t('firmware.flashProgress.showDetails') }}
      </summary>
      <LogPane :log="cleanLog" max-class="max-h-48" class="mt-1" reportable />
    </details>
  </div>
</template>
