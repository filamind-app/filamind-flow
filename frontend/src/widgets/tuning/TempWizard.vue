<script setup lang="ts">
/** Temperature tuning wizard. Unlike PA/retraction this uses TUNING_TOWER BAND mode (stepwise,
 *  one temperature per band so the hotend can settle), so it has its own component: a heater
 *  picker + a per-band Z-range/temperature table. Pick the cleanest height -> its band's
 *  temperature -> gated SET_HEATER_TEMPERATURE.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { applyTemp, planTemp } from './api'
import { HEATERS, defaultTempParams, type TempBand, type TempTowerPlan } from './types'

const { t } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string

const params = ref(defaultTempParams())
const plan = ref<TempTowerPlan | null>(null)
const bestHeight = ref<number | null>(null)
const error = ref<string | null>(null)
const notice = ref<{ text: string; ok: boolean } | null>(null)
const planning = ref(false)
const applying = ref(false)

/** The band the chosen height falls into (last band is inclusive of the tower top). */
const chosenBand = computed<TempBand | null>(() => {
  const p = plan.value
  const h = bestHeight.value
  if (!p || h == null) return null
  return (
    p.bands.find(
      (b, i) => h >= b.z_low && (h < b.z_high || (i === p.bands.length - 1 && h <= b.z_high)),
    ) ?? null
  )
})

async function doPlan(): Promise<void> {
  planning.value = true
  error.value = null
  notice.value = null
  try {
    plan.value = await planTemp(params.value)
    bestHeight.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    planning.value = false
  }
}

async function doApply(): Promise<void> {
  const band = chosenBand.value
  if (!band) return
  applying.value = true
  error.value = null
  try {
    const res = await applyTemp(params.value.heater, band.temp)
    notice.value = { text: tt(`tuning.temp.apply.${res.code}`, res.params ?? {}), ok: res.ok }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="space-y-3">
    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>

    <!-- Step 1: configure + plan the tower -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.temp.step1') }}</p>
      <div class="grid grid-cols-2 gap-2">
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.temp.params.heater') }}
          <select v-model="params.heater" class="nb-input">
            <option v-for="h in HEATERS" :key="h" :value="h">
              {{ t(`tuning.temp.heaters.${h}`) }}
            </option>
          </select>
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.temp.params.start') }}
          <input v-model.number="params.start" type="number" step="5" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.temp.params.factor') }}
          <input v-model.number="params.factor" type="number" step="0.1" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.temp.params.band') }}
          <input v-model.number="params.band" type="number" step="1" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.temp.params.height') }}
          <input v-model.number="params.height" type="number" step="1" class="nb-input" />
        </label>
      </div>
      <button class="nb-btn bg-brand-lime px-3 py-1" :disabled="planning" @click="doPlan">
        {{ t('tuning.temp.plan') }}
      </button>
    </div>

    <!-- The TUNING_TOWER command + the per-band Z-range / temperature table -->
    <div v-if="plan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.temp.command') }}</p>
      <p class="text-[11px] opacity-70">{{ t('tuning.temp.commandHint') }}</p>
      <pre
        class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
        >{{ plan.command }}</pre>
      <table class="w-full text-[11px]">
        <thead>
          <tr class="text-start opacity-70">
            <th class="text-start font-bold">{{ t('tuning.temp.table.range') }}</th>
            <th class="text-start font-bold">{{ t('tuning.temp.table.temp') }}</th>
          </tr>
        </thead>
        <tbody class="font-mono">
          <tr
            v-for="b in plan.bands"
            :key="b.z_low"
            :class="chosenBand === b ? 'bg-brand-cyan/30' : ''"
          >
            <td>{{ b.z_low }} - {{ b.z_high }}</td>
            <td>{{ b.temp }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Step 2: enter the best height -> band temperature -> apply -->
    <div v-if="plan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.temp.step2') }}</p>
      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('tuning.temp.bestHeight') }}
        <input v-model.number="bestHeight" type="number" step="1" class="nb-input" />
      </label>
      <p v-if="chosenBand" class="text-xs">
        {{ tt('tuning.temp.computed', { temp: chosenBand.temp }) }}
      </p>
      <p v-else-if="bestHeight != null" class="text-[11px] opacity-70">
        {{ t('tuning.temp.noBand') }}
      </p>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1"
        :disabled="!chosenBand || applying"
        @click="doApply"
      >
        {{ t('tuning.temp.applyButton') }}
      </button>
    </div>

    <p
      v-if="notice"
      class="nb-card px-2 py-1 text-xs"
      :class="notice.ok ? 'bg-brand-lime' : 'bg-brand-yellow text-ink'"
      role="status"
    >
      {{ notice.text }}
    </p>
  </div>
</template>
