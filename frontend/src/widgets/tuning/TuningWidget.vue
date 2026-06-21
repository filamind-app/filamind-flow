<script setup lang="ts">
/** Tuning wizards (suite-only / flow-A). First wizard: Pressure Advance - plan a TUNING_TOWER,
 *  print it, read the best Z height off the result, and the wizard computes + applies the matching
 *  PA (gated). More wizards (flow / temp / retraction) slot in here later.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { applyPa, planPa } from './api'
import { defaultParams, type PaTowerPlan } from './types'

const { t } = useI18n({ useScope: 'global' })

const params = ref(defaultParams())
const plan = ref<PaTowerPlan | null>(null)
const bestHeight = ref<number | null>(null)
const error = ref<string | null>(null)
const notice = ref<{ text: string; ok: boolean } | null>(null)
const planning = ref(false)
const applying = ref(false)

const computedPa = computed(() => {
  const p = plan.value
  if (!p || bestHeight.value == null) return null
  return Math.round((p.start + p.factor * bestHeight.value) * 10000) / 10000
})

async function doPlan(): Promise<void> {
  planning.value = true
  error.value = null
  notice.value = null
  try {
    plan.value = await planPa(params.value)
    bestHeight.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    planning.value = false
  }
}

async function doApply(): Promise<void> {
  if (computedPa.value == null) return
  applying.value = true
  error.value = null
  try {
    const res = await applyPa(computedPa.value)
    const tt = t as unknown as (key: string, named: Record<string, unknown>) => string
    notice.value = { text: tt(`tuning.pa.apply.${res.code}`, res.params ?? {}), ok: res.ok }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('tuning.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="tuning"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('tuning.help.guide')"
        :title="t('tuning.help.guideTitle')"
        :close-label="t('tuning.help.close')"
      />
    </div>

    <h3 class="font-display text-base font-bold">{{ t('tuning.pa.title') }}</h3>

    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>

    <!-- Step 1: configure + plan the tower -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.pa.step1') }}</p>
      <div class="grid grid-cols-3 gap-2">
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.params.start') }}
          <input v-model.number="params.start" type="number" step="0.005" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.params.factor') }}
          <input v-model.number="params.factor" type="number" step="0.001" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('tuning.params.height') }}
          <input v-model.number="params.height" type="number" step="1" class="nb-input" />
        </label>
      </div>
      <button class="nb-btn bg-brand-lime px-3 py-1" :disabled="planning" @click="doPlan">
        {{ t('tuning.pa.plan') }}
      </button>
    </div>

    <!-- The TUNING_TOWER command + the height->PA table -->
    <div v-if="plan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.pa.command') }}</p>
      <p class="text-[11px] opacity-70">{{ t('tuning.pa.commandHint') }}</p>
      <pre
        class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
        >{{ plan.command }}</pre
      >
      <table class="w-full text-[11px]">
        <thead>
          <tr class="text-start opacity-70">
            <th class="text-start font-bold">{{ t('tuning.pa.table.height') }}</th>
            <th class="text-start font-bold">{{ t('tuning.pa.table.pa') }}</th>
          </tr>
        </thead>
        <tbody class="font-mono">
          <tr v-for="s in plan.samples" :key="s.height">
            <td>{{ s.height }}</td>
            <td>{{ s.pa }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Step 2: enter the best height -> computed PA -> apply -->
    <div v-if="plan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('tuning.pa.step2') }}</p>
      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('tuning.pa.bestHeight') }}
        <input v-model.number="bestHeight" type="number" step="0.2" class="nb-input" />
      </label>
      <p v-if="computedPa != null" class="text-xs">
        {{ t('tuning.pa.computed', { pa: computedPa }) }}
      </p>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1"
        :disabled="computedPa == null || applying"
        @click="doApply"
      >
        {{ t('tuning.pa.applyButton') }}
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
