<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { ApiError, fetchHotends, planMaxFlow, runMaxFlow } from './api'
import { CANCELLED, cancelMaxFlow, flowRun, reattachMaxFlow } from './supervised'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { HotendRow, MaxFlowParams, MaxFlowPlan, MaxFlowResult } from './types'

const { t, tm, rt } = useI18n({ useScope: 'global' })
// Array message → raw nodes; resolve each to a string (same pattern as HelpDrawer).
const tmArr = tm as unknown as (key: string) => unknown[]
const rtt = rt as unknown as (node: unknown) => string
const safetyItems = computed(() => tmArr('maxFlow.safety.items').map(rtt))

const params = reactive<MaxFlowParams>({
  temperature: 240,
  start_flow: 5,
  end_flow: 25,
  step_flow: 2.5,
  filament_diameter: 1.75,
  extrude_per_step: 5,
  samples_per_step: 20,
  driver: 'tmc2209',
})

const hotends = ref<HotendRow[]>([])
const selectedHotend = ref<string | null>(null)
const plan = ref<MaxFlowPlan | null>(null)
const planning = ref(false)
const planErr = ref<string | null>(null)
const ack = ref(false)
const confirmOpen = ref(false)
const running = ref(false)
const result = ref<MaxFlowResult | null>(null)
const runErr = ref<string | null>(null)

const hotendOptions = computed(() =>
  hotends.value.map((h) => ({
    value: h.name,
    label: h.name,
    sublabel:
      h.expected_max_flow_mm3s != null
        ? t('maxFlow.params.hotendHint', { flow: h.expected_max_flow_mm3s })
        : '',
  })),
)

function resetDownstream(): void {
  plan.value = null
  result.value = null
  runErr.value = null
  ack.value = false
  confirmOpen.value = false
}

watch(selectedHotend, (name) => {
  const row = hotends.value.find((h) => h.name === name)
  if (row) {
    if (typeof row.suggested_temp_c === 'number') params.temperature = row.suggested_temp_c
    if (typeof row.expected_max_flow_mm3s === 'number') {
      params.end_flow = Math.max(
        params.start_flow + params.step_flow,
        Math.ceil(row.expected_max_flow_mm3s * 1.4),
      )
    }
  }
})

// Any parameter edit invalidates a previous plan/result — force a fresh preview.
watch(params, () => resetDownstream(), { deep: true })

async function doPlan(): Promise<void> {
  planning.value = true
  planErr.value = null
  result.value = null
  try {
    plan.value = await planMaxFlow({ ...params })
  } catch (e) {
    planErr.value = describeError(e)
    plan.value = null
  } finally {
    planning.value = false
  }
}

const runInfo = ref<string | null>(null)

async function doRun(): Promise<void> {
  running.value = true
  runErr.value = null
  runInfo.value = null
  try {
    result.value = await runMaxFlow({ ...params })
    confirmOpen.value = false
  } catch (e) {
    confirmOpen.value = false
    if (e instanceof Error && e.message === CANCELLED) {
      runInfo.value = t('maxFlow.run.cancelled')
    } else {
      runErr.value =
        e instanceof ApiError && e.status === 409 ? t('maxFlow.run.busy') : describeError(e)
    }
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  fetchHotends()
    .then((rows) => (hotends.value = rows))
    .catch(() => {})
  // After a reload: resume a still-running test, or collect the result a dropped tab missed.
  try {
    const resumed = await reattachMaxFlow()
    if (resumed) {
      result.value = resumed
      runInfo.value = t('maxFlow.run.reattached')
    }
  } catch (e) {
    if (!(e instanceof Error && e.message === CANCELLED)) runErr.value = describeError(e)
  }
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('maxFlow.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="maxFlow"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="maxFlow.help.steps"
          :button-label="t('maxFlow.help.guide')"
          :title="t('maxFlow.help.guideTitle')"
          :close-label="t('maxFlow.help.close')"
          :steps-title="t('maxFlow.help.howToRead')"
        />
        <HelpIllo illo="flow" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- Parameters -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('maxFlow.params.title') }}</p>
      <label class="block">
        <span class="mb-1 block text-[11px] opacity-70">{{ t('maxFlow.params.hotend') }}</span>
        <ComboSelect
          v-model="selectedHotend"
          :options="hotendOptions"
          :placeholder="t('maxFlow.params.hotendNone')"
          clearable
        />
      </label>
      <div class="grid grid-cols-2 gap-2 font-mono text-[11px] sm:grid-cols-3">
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.temperature') }}</span>
          <input
            v-model.number="params.temperature"
            type="number"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.filamentDiameter') }}</span>
          <input
            v-model.number="params.filament_diameter"
            type="number"
            step="0.01"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.samples') }}</span>
          <input
            v-model.number="params.samples_per_step"
            type="number"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.startFlow') }}</span>
          <input
            v-model.number="params.start_flow"
            type="number"
            step="0.5"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.endFlow') }}</span>
          <input
            v-model.number="params.end_flow"
            type="number"
            step="0.5"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.stepFlow') }}</span>
          <input
            v-model.number="params.step_flow"
            type="number"
            step="0.5"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
        <label class="block">
          <span class="mb-0.5 block opacity-70">{{ t('maxFlow.params.extrudePerStep') }}</span>
          <input
            v-model.number="params.extrude_per_step"
            type="number"
            class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1"
          />
        </label>
      </div>
      <button class="nb-btn bg-brand-cyan px-3 py-1 text-xs" :disabled="planning" @click="doPlan">
        {{ t('maxFlow.plan.button') }}
      </button>
      <p v-if="planErr" class="font-mono text-[11px] text-brand-red">{{ planErr }}</p>
    </div>

    <!-- Plan preview -->
    <div v-if="plan" class="nb-card space-y-2 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('maxFlow.plan.title') }}</p>
      <div class="flex flex-wrap gap-2 font-mono text-[11px]">
        <span class="nb-card bg-paper px-2 py-0.5">{{
          t('maxFlow.plan.stepCount', { count: plan.step_count })
        }}</span>
        <span class="nb-card bg-paper px-2 py-0.5">{{
          t('maxFlow.plan.totalExtrude', { mm: plan.total_extrude_mm })
        }}</span>
        <span class="nb-card bg-paper px-2 py-0.5">
          {{
            plan.stallguard_field
              ? t('maxFlow.plan.sgField', { field: plan.stallguard_field })
              : t('maxFlow.plan.sgFieldUnknown')
          }}
        </span>
      </div>
      <table class="w-full border-collapse font-mono text-[11px]">
        <thead>
          <tr class="text-start opacity-60">
            <th class="py-0.5 pe-2 text-start font-bold">{{ t('maxFlow.plan.flowHead') }}</th>
            <th class="py-0.5 text-start font-bold">{{ t('maxFlow.plan.feedrateHead') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(s, i) in plan.steps" :key="i">
            <td class="py-0.5 pe-2">{{ s.flow_mm3s }}</td>
            <td class="py-0.5">{{ s.feedrate_mm_min }}</td>
          </tr>
        </tbody>
      </table>
      <p class="rounded bg-brand-yellow/20 p-1.5 text-[11px]">⚠ {{ t('maxFlow.plan.warning') }}</p>
    </div>

    <!-- Safety checklist + run gate -->
    <div v-if="plan" class="nb-card space-y-2 border-brand-red bg-brand-red/10 p-2">
      <p class="text-xs font-bold">{{ t('maxFlow.safety.title') }}</p>
      <ul class="list-disc space-y-0.5 ps-5 text-[11px] opacity-90">
        <li v-for="(item, i) in safetyItems" :key="i">{{ item }}</li>
      </ul>
      <label class="flex items-center gap-2 text-[11px]">
        <input v-model="ack" type="checkbox" />
        {{ t('maxFlow.safety.ack') }}
      </label>
      <p class="text-[10px] opacity-60">{{ t('maxFlow.safety.note') }}</p>
      <button
        class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
        :disabled="!ack || running"
        @click="confirmOpen = true"
      >
        {{ running ? t('maxFlow.run.running') : t('maxFlow.run.button') }}
      </button>
    </div>

    <!-- Run confirm dialog -->
    <div v-if="confirmOpen" class="nb-card space-y-2 border-brand-red bg-brand-yellow/20 p-2">
      <p class="text-xs font-bold">{{ t('maxFlow.run.confirmTitle') }}</p>
      <p class="text-[11px] opacity-80">
        {{
          t('maxFlow.run.confirmBody', {
            temp: params.temperature,
            mm: plan?.total_extrude_mm ?? 0,
          })
        }}
      </p>
      <div class="flex gap-2">
        <button
          class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
          :disabled="running"
          @click="doRun"
        >
          {{ t('maxFlow.run.confirm') }}
        </button>
        <button
          class="nb-btn bg-surface px-2 py-1 text-xs"
          :disabled="running"
          @click="confirmOpen = false"
        >
          {{ t('maxFlow.run.cancel') }}
        </button>
      </div>
    </div>

    <!-- Supervised-run progress: per-step counter + a cancel that always cuts the heater -->
    <div v-if="flowRun.status !== 'idle'" class="nb-card space-y-1 bg-surface p-2">
      <div class="flex items-center justify-between gap-2 font-mono text-[11px]">
        <span v-if="flowRun.progress">
          {{
            t('maxFlow.run.progress', {
              step: flowRun.progress.step,
              total: flowRun.progress.total,
              flow: Number(flowRun.progress.detail?.flow ?? 0).toFixed(1),
            })
          }}
        </span>
        <span v-else>{{ t('maxFlow.run.starting') }}</span>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-[10px] text-paper"
          :disabled="flowRun.status === 'cancelling'"
          @click="cancelMaxFlow"
        >
          {{
            flowRun.status === 'cancelling' ? t('maxFlow.run.cancelling') : t('maxFlow.run.abort')
          }}
        </button>
      </div>
      <div
        v-if="flowRun.progress"
        class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper"
      >
        <div
          class="h-full bg-brand-cyan"
          :style="{
            width:
              Math.round((flowRun.progress.step / Math.max(1, flowRun.progress.total)) * 100) + '%',
          }"
        ></div>
      </div>
      <p class="text-[10px] opacity-60">{{ t('maxFlow.run.abortNote') }}</p>
    </div>

    <p v-if="runInfo" class="nb-card bg-brand-cyan/20 p-2 font-mono text-[11px]">{{ runInfo }}</p>
    <p v-if="runErr" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">{{ runErr }}</p>

    <!-- Result -->
    <div v-if="result" class="nb-card space-y-2 bg-brand-lime/20 p-2">
      <p class="text-xs font-bold">{{ t('maxFlow.result.title') }}</p>
      <p class="font-mono text-sm">
        <b>{{ t('maxFlow.result.maxFlow') }}:</b>
        {{ result.max_flow_mm3s ?? '—' }} {{ t('maxFlow.result.units') }}
      </p>
      <p class="font-mono text-[11px]">
        {{
          result.slip_flow != null
            ? t('maxFlow.result.slipAt', { flow: result.slip_flow })
            : t('maxFlow.result.noSlip')
        }}
      </p>
      <p v-if="!result.sg_samples_seen" class="rounded bg-brand-red/20 p-1.5 text-[11px]">
        ⚠ {{ t('maxFlow.run.noSg') }}
      </p>
      <div v-if="result.recommend.max != null" class="space-y-0.5 font-mono text-[11px]">
        <p class="font-bold">{{ t('maxFlow.result.recommendTitle') }}</p>
        <p>
          {{ t('maxFlow.result.conservative') }}: {{ result.recommend.conservative }}
          {{ t('maxFlow.result.units') }}
        </p>
        <p>
          {{ t('maxFlow.result.balanced') }}: {{ result.recommend.balanced }}
          {{ t('maxFlow.result.units') }}
        </p>
      </div>
      <details class="text-[11px]">
        <summary class="cursor-pointer opacity-70">{{ t('maxFlow.result.reason') }}</summary>
        <p class="mt-1 font-mono opacity-80">{{ result.reason }}</p>
        <table class="mt-1 w-full border-collapse font-mono text-[10px]">
          <thead>
            <tr class="text-start opacity-60">
              <th class="pe-2 text-start">{{ t('maxFlow.plan.flowHead') }}</th>
              <th class="pe-2 text-start">IQR</th>
              <th class="text-start">CV%</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in result.steps" :key="i">
              <td class="pe-2">{{ s.flow }}</td>
              <td class="pe-2">{{ s.iqr.toFixed(1) }}</td>
              <td>{{ s.cv_pct.toFixed(1) }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </div>
  </div>
</template>
