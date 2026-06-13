<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { ApiError, fetchExtruderDriver, fetchHotends, planMaxFlow, runMaxFlow } from './api'
import { fetchCameras } from './camera'
import CameraView from './CameraView.vue'
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
  park_for_view: true,
  auto_stealthchop: false,
})

/** Webcams configured on the printer — the live view is shown during a run when one exists. */
const cameras = ref<{ name: string; service: string }[]>([])
const cameraName = computed(() => cameras.value[0]?.name)
const cameraAvailable = computed(() => cameras.value.length > 0)

/** SG4 drivers (TMC2209/2240) read StallGuard only in StealthChop — the auto-StealthChop option
 *  (temporarily set + revert a stealthchop_threshold) is offered only for them. */
const SG4_DRIVERS = ['tmc2209', 'tmc2240']
const isSg4 = computed(() => SG4_DRIVERS.includes(params.driver))

const hotends = ref<HotendRow[]>([])
const selectedHotend = ref<string | null>(null)
const plan = ref<MaxFlowPlan | null>(null)
const planning = ref(false)
const planErr = ref<string | null>(null)
const ack = ref(false)
const confirmOpen = ref(false)
const running = ref(false)
const result = ref<MaxFlowResult | null>(null)
/** When the shown result came from a previous session (localStorage), its timestamp. */
const resultFrom = ref<string | null>(null)
/** The TMC model detected on the extruder (preselects the driver param honestly). */
const detectedDriver = ref<string | null>(null)
const DRIVER_OPTIONS = ['tmc2209', 'tmc2208', 'tmc2226', 'tmc2130', 'tmc2240', 'tmc5160', 'tmc2660']
const LAST_RESULT_KEY = 'filamind-maxflow-last'

function rememberResult(r: MaxFlowResult): void {
  try {
    localStorage.setItem(LAST_RESULT_KEY, JSON.stringify({ at: new Date().toISOString(), r }))
  } catch {
    /* best-effort */
  }
}
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

/** Pre-ramp phases report step 0 with a `phase` tag; the ramp reports step/total + flow. */
const PRE_RAMP_PHASES = ['enabling', 'homing', 'centering', 'heating', 'checking', 'reverting']
const phaseLabel = computed(() => {
  const p = flowRun.progress
  if (!p) return t('maxFlow.run.starting')
  const phase = String(p.detail?.phase ?? '')
  if (PRE_RAMP_PHASES.includes(phase)) {
    return t(`maxFlow.run.phase.${phase}`)
  }
  if (p.step > 0) {
    return t('maxFlow.run.progress', {
      step: p.step,
      total: p.total,
      flow: Number(p.detail?.flow ?? 0).toFixed(1),
    })
  }
  return t('maxFlow.run.starting')
})

/** The 5 core phases shown as a horizontal stepper; `enabling`/`reverting` are config bookends. */
const STEPPER = [
  { key: 'home', phases: ['homing'] },
  { key: 'center', phases: ['centering'] },
  { key: 'heat', phases: ['heating'] },
  { key: 'check', phases: ['checking'] },
  { key: 'ramp', phases: ['ramp'] },
] as const
/** Index of the active stepper cell from the current phase (−1 before it starts / during bookends). */
const stepperActive = computed(() => {
  const phase = String(flowRun.progress?.detail?.phase ?? '')
  if (phase === 'reverting') return STEPPER.length // all done, restoring config
  return STEPPER.findIndex((s) => (s.phases as readonly string[]).includes(phase))
})
/** True when a finished run produced no usable StallGuard samples (result is unreliable). */
const noSignal = computed(() => result.value != null && result.value.sg_samples_seen === false)

async function doRun(): Promise<void> {
  running.value = true
  runErr.value = null
  runInfo.value = null
  try {
    result.value = await runMaxFlow({ ...params })
    resultFrom.value = null
    rememberResult(result.value)
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
  // A webcam is optional — only show the live view if the printer has one configured.
  fetchCameras()
    .then((cams) => (cameras.value = cams))
    .catch(() => {})
  // Detect the extruder's real TMC model so the driver param starts honest (a 2240/5160
  // extruder would otherwise hit a preflight refusal the user can't fix from here).
  fetchExtruderDriver()
    .then((d) => {
      detectedDriver.value = d
      if (d) params.driver = d
    })
    .catch(() => {})
  // After a reload: resume a still-running test, or collect the result a dropped tab missed.
  try {
    const resumed = await reattachMaxFlow()
    if (resumed) {
      result.value = resumed
      runInfo.value = t('maxFlow.run.reattached')
      rememberResult(resumed)
      return
    }
  } catch (e) {
    if (!(e instanceof Error && e.message === CANCELLED)) runErr.value = describeError(e)
  }
  // Nothing live — restore the last session's result so minutes of grinding aren't lost to
  // a navigation (clearly labeled with when it was measured).
  try {
    const stored = localStorage.getItem(LAST_RESULT_KEY)
    if (stored && !result.value) {
      const parsed = JSON.parse(stored) as { at: string; r: MaxFlowResult }
      result.value = parsed.r
      resultFrom.value = parsed.at
    }
  } catch {
    /* ignore a corrupt entry */
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
          <span class="mb-0.5 block opacity-70">
            {{ t('maxFlow.params.driver') }}
            <span v-if="detectedDriver" class="opacity-60">
              ({{ t('maxFlow.params.driverDetected') }})</span
            >
          </span>
          <select
            v-model="params.driver"
            class="w-full rounded-brutal border-2 border-ink bg-surface px-1.5 py-1 font-mono text-[11px]"
          >
            <option v-for="d in DRIVER_OPTIONS" :key="d" :value="d">
              {{ d.toUpperCase() }}{{ d === detectedDriver ? ' ✓' : '' }}
            </option>
          </select>
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
      <!-- SG4 only: offer to flip the extruder to StealthChop just for the test, then undo it. -->
      <label
        v-if="isSg4"
        class="flex items-start gap-2 rounded-brutal border-2 border-dashed border-ink/40 bg-paper/60 p-1.5 text-[11px]"
      >
        <input v-model="params.auto_stealthchop" type="checkbox" class="mt-0.5" />
        <span>
          <span class="font-bold">{{ t('maxFlow.params.autoStealthchop') }}</span>
          <span class="block text-[10px] opacity-70">{{
            t('maxFlow.params.autoStealthchopHint')
          }}</span>
        </span>
      </label>
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
      <p class="text-[10px] opacity-70">🎯 {{ t('maxFlow.run.parkNote') }}</p>
      <p v-if="cameraAvailable" class="text-[10px] opacity-70">
        📷 {{ t('maxFlow.camera.willShow') }}
      </p>
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

    <!-- Supervised-run progress: phase/step + live camera + a cancel that always cuts the heater.
         When the corner PiP is shown, reserve inline-end space so it never covers the stepper. -->
    <div
      v-if="flowRun.status !== 'idle'"
      role="status"
      aria-live="polite"
      class="nb-card space-y-2 bg-surface p-2"
      :class="cameraAvailable ? 'sm:pe-[300px]' : ''"
    >
      <div class="flex items-center justify-between gap-2 font-mono text-[11px]">
        <span class="font-bold">{{ phaseLabel }}</span>
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
        class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper"
        :class="{ 'animate-pulse': !flowRun.progress || flowRun.progress.step === 0 }"
      >
        <div
          class="h-full bg-brand-cyan transition-[width] duration-300"
          :style="{
            width:
              Math.round(
                ((flowRun.progress?.step ?? 0) / Math.max(1, flowRun.progress?.total ?? 1)) * 100,
              ) + '%',
          }"
        ></div>
      </div>
      <!-- Phase stepper: home → center → heat → check → ramp (done = lime, active = cyan). -->
      <div class="flex items-stretch gap-1">
        <div
          v-for="(s, i) in STEPPER"
          :key="s.key"
          class="flex-1 rounded-brutal border-2 border-ink px-1 py-1 text-center text-[9px] font-bold uppercase tracking-wide transition-colors"
          :class="
            i < stepperActive
              ? 'bg-brand-lime'
              : i === stepperActive
                ? 'bg-brand-cyan'
                : 'bg-paper opacity-50'
          "
        >
          {{ t(`maxFlow.run.step.${s.key}`) }}
        </div>
      </div>
      <p class="text-[10px] opacity-60">{{ t('maxFlow.run.abortNote') }}</p>
    </div>

    <!-- Live nozzle camera as a fixed, compact PiP while a run is active (only when one exists). -->
    <CameraView
      v-if="cameraAvailable && flowRun.status !== 'idle'"
      pip
      :active="true"
      :name="cameraName"
    />

    <p v-if="runInfo" class="nb-card bg-brand-cyan/20 p-2 font-mono text-[11px]">{{ runInfo }}</p>
    <p v-if="runErr" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">{{ runErr }}</p>

    <!-- Result -->
    <div
      v-if="result"
      class="nb-card space-y-2 p-2"
      :class="noSignal ? 'border-brand-red bg-brand-red/10' : 'bg-brand-lime/20'"
    >
      <p class="text-xs font-bold">{{ t('maxFlow.result.title') }}</p>
      <p v-if="resultFrom" class="font-mono text-[10px] opacity-60">
        {{ t('maxFlow.result.fromBefore', { at: resultFrom.slice(0, 16).replace('T', ' ') }) }}
      </p>

      <!-- No StallGuard signal → the number is not a real measurement. Say so, first and loud. -->
      <div v-if="noSignal" class="space-y-1 rounded border-2 border-brand-red bg-brand-red/15 p-2">
        <p class="text-[11px] font-bold text-brand-red">
          ⚠ {{ t('maxFlow.result.unreliableTitle') }}
        </p>
        <p class="text-[11px] opacity-90">{{ t('maxFlow.run.noSg') }}</p>
      </div>

      <p class="font-mono text-sm">
        <b>{{ t('maxFlow.result.maxFlow') }}:</b>
        {{ result.max_flow_mm3s ?? '—' }} {{ t('maxFlow.result.units') }}
        <span v-if="noSignal" class="text-[10px] opacity-70"
          >({{ t('maxFlow.result.unmeasured') }})</span
        >
      </p>
      <p class="font-mono text-[11px]">
        {{
          result.slip_flow != null
            ? t('maxFlow.result.slipAt', { flow: result.slip_flow })
            : t('maxFlow.result.noSlip')
        }}
      </p>
      <div
        v-if="!noSignal && result.recommend.max != null"
        class="space-y-0.5 font-mono text-[11px]"
      >
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
