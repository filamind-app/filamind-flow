<script setup lang="ts">
/** Flow (extrusion) calibration. Klipper has no live flow override, so this is a guided
 *  calculator: command a known length, measure what actually came out, and it corrects
 *  rotation_distance. The result goes in printer.cfg (SAVE_CONFIG + restart) - never applied live.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { computeFlow, getExtruderRotationDistance } from './api'
import type { FlowComputeResult } from './types'

const { t } = useI18n({ useScope: 'global' })

const requested = ref(100)
const measured = ref<number | null>(null)
const currentRd = ref<number | null>(null)
const result = ref<FlowComputeResult | null>(null)
const error = ref<string | null>(null)
const loadingCurrent = ref(false)
const calculating = ref(false)
const couldNotRead = ref(false)

const canCalc = computed(
  () =>
    requested.value > 0 &&
    measured.value != null &&
    measured.value > 0 &&
    currentRd.value != null &&
    currentRd.value > 0,
)

const snippet = computed(() =>
  result.value ? `[extruder]\nrotation_distance: ${result.value.new_rotation_distance}` : '',
)

async function fetchCurrent(): Promise<void> {
  loadingCurrent.value = true
  error.value = null
  couldNotRead.value = false
  try {
    const res = await getExtruderRotationDistance()
    currentRd.value = res.rotation_distance
    couldNotRead.value = res.rotation_distance == null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loadingCurrent.value = false
  }
}

async function doCalc(): Promise<void> {
  if (!canCalc.value) return
  calculating.value = true
  error.value = null
  try {
    result.value = await computeFlow(requested.value, measured.value!, currentRd.value!)
  } catch (e) {
    error.value = describeError(e)
  } finally {
    calculating.value = false
  }
}

onMounted(fetchCurrent)
</script>

<template>
  <div class="space-y-3">
    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>

    <!-- Step 1: measure -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.flow.step1') }}</p>
      <div class="grid grid-cols-2 gap-2">
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.flow.requested') }}
          <input v-model.number="requested" type="number" step="10" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.flow.measured') }}
          <input v-model.number="measured" type="number" step="0.5" class="nb-input" />
        </label>
      </div>
      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('tuning.flow.current') }}
        <div class="flex gap-2">
          <input v-model.number="currentRd" type="number" step="0.001" class="nb-input flex-1" />
          <button
            class="nb-btn bg-surface px-2 py-1 text-xs"
            :disabled="loadingCurrent"
            @click="fetchCurrent"
          >
            {{ t('tuning.flow.fetch') }}
          </button>
        </div>
      </label>
      <p v-if="couldNotRead" class="text-[11px] opacity-70">{{ t('tuning.flow.noCurrent') }}</p>
      <button
        class="nb-btn bg-brand-lime px-3 py-1"
        :disabled="!canCalc || calculating"
        @click="doCalc"
      >
        {{ t('tuning.flow.calc') }}
      </button>
    </div>

    <!-- Step 2: correction -->
    <div v-if="result" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.flow.step2') }}</p>
      <p class="text-sm font-bold">
        {{ t('tuning.flow.result', { value: result.new_rotation_distance }) }}
      </p>
      <p class="text-xs opacity-80">
        {{ t('tuning.flow.flowPercent', { percent: result.flow_percent }) }}
      </p>
      <p class="text-[11px] opacity-70">{{ t('tuning.flow.snippetTitle') }}</p>
      <pre
        class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
        >{{ snippet }}</pre>
      <p class="nb-card bg-brand-yellow px-2 py-1 text-[11px] text-ink" role="note">
        {{ t('tuning.flow.notLive') }}
      </p>
    </div>
  </div>
</template>
