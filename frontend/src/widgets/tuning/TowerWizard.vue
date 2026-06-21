<script setup lang="ts">
/** Generic TUNING_TOWER wizard: configure -> plan -> show command + height->value table ->
 *  enter the best Z height -> computed value -> gated apply. Pressure Advance and retraction are
 *  both instances of this (they differ only in their i18n base, sample value key, and api calls).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import type { ApplyResult, TowerParams, TowerPlan } from './types'

const props = defineProps<{
  /** i18n base for this wizard, e.g. 'tuning.pa' or 'tuning.retraction'. */
  base: string
  /** i18n base for the three param labels, e.g. 'tuning.params'. */
  paramsBase: string
  /** Sample/column/computed value key: 'pa' for Pressure Advance, 'value' for retraction. */
  valueKey: string
  defaults: TowerParams
  plan: (params: TowerParams) => Promise<TowerPlan>
  apply: (value: number) => Promise<ApplyResult>
}>()

const { t } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string
const k = (suffix: string): string => `${props.base}.${suffix}`

const params = ref<TowerParams>({ ...props.defaults })
const towerPlan = ref<TowerPlan | null>(null)
const bestHeight = ref<number | null>(null)
const error = ref<string | null>(null)
const notice = ref<{ text: string; ok: boolean } | null>(null)
const planning = ref(false)
const applying = ref(false)

const computedValue = computed<number | null>(() => {
  const p = towerPlan.value
  if (!p || bestHeight.value == null) return null
  return Math.round((p.start + p.factor * bestHeight.value) * 10000) / 10000
})

async function doPlan(): Promise<void> {
  planning.value = true
  error.value = null
  notice.value = null
  try {
    towerPlan.value = await props.plan(params.value)
    bestHeight.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    planning.value = false
  }
}

async function doApply(): Promise<void> {
  if (computedValue.value == null) return
  applying.value = true
  error.value = null
  try {
    const res = await props.apply(computedValue.value)
    notice.value = { text: tt(k(`apply.${res.code}`), res.params ?? {}), ok: res.ok }
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
      <p class="text-xs font-bold">{{ t(k('step1')) }}</p>
      <div class="grid grid-cols-3 gap-2">
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t(`${paramsBase}.start`) }}
          <input v-model.number="params.start" type="number" step="0.005" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t(`${paramsBase}.factor`) }}
          <input v-model.number="params.factor" type="number" step="0.001" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t(`${paramsBase}.height`) }}
          <input v-model.number="params.height" type="number" step="1" class="nb-input" />
        </label>
      </div>
      <button class="nb-btn bg-brand-lime px-3 py-1" :disabled="planning" @click="doPlan">
        {{ t(k('plan')) }}
      </button>
    </div>

    <!-- The TUNING_TOWER command + the height->value table -->
    <div v-if="towerPlan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t(k('command')) }}</p>
      <p class="text-[11px] opacity-70">{{ t(k('commandHint')) }}</p>
      <pre
        class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
        >{{ towerPlan.command }}</pre
      >
      <table class="w-full text-[11px]">
        <thead>
          <tr class="text-start opacity-70">
            <th class="text-start font-bold">{{ t(k('table.height')) }}</th>
            <th class="text-start font-bold">{{ t(k(`table.${valueKey}`)) }}</th>
          </tr>
        </thead>
        <tbody class="font-mono">
          <tr v-for="s in towerPlan.samples" :key="s.height">
            <td>{{ s.height }}</td>
            <td>{{ s[valueKey] }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Step 2: enter the best height -> computed value -> apply -->
    <div v-if="towerPlan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t(k('step2')) }}</p>
      <label class="flex flex-col gap-0.5 text-xs">
        {{ t(k('bestHeight')) }}
        <input v-model.number="bestHeight" type="number" step="0.2" class="nb-input" />
      </label>
      <p v-if="computedValue != null" class="text-xs">
        {{ tt(k('computed'), { [valueKey]: computedValue }) }}
      </p>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1"
        :disabled="computedValue == null || applying"
        @click="doApply"
      >
        {{ t(k('applyButton')) }}
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
