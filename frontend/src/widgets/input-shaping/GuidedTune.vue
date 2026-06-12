<script setup lang="ts">
/** Guided tuning wizard — walks Noise → Belts → Shaper X → Shaper Y with automated
 *  pass/fail gates (reusing the existing scorers) and concrete next-step suggestions.
 *  A thin client conductor: it calls the SAME endpoints as the manual panel and emits
 *  each shaper result up via `analyzed`, so the combined config + grade-history just work.
 */
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { compareBelts, measureNoise, runLiveTest, runVibrationsProfile } from './api'
import { beltVerdict } from './compare'
import {
  type Gate,
  type GateStatus,
  type StepId,
  gateBelts,
  gateNoise,
  gateShaper,
  gateVibrations,
  nextStep,
  PA_TOWER_GCODE,
  STEPS,
} from './guided'
import {
  recommendBelts,
  recommendNoise,
  recommendPressure,
  recommendShaper,
  recommendVibrations,
  type Suggestion,
} from './recommend'
import type { BeltComparison, NoiseResult, ShaperAnalysis, VibrationsProfile } from './types'
import VibrationsProfileView from './VibrationsProfile.vue'

const emit = defineEmits<{ analyzed: [ShaperAnalysis]; exit: [] }>()

const { t } = useI18n({ useScope: 'global' })
// Step keys are built from the (typed) step id at runtime — use a string-accepting view of t.
const tt = t as unknown as (key: string) => string

type StepState = GateStatus | 'pending' | 'skipped'

const idx = ref(0)
const ready = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const gate = ref<Gate | null>(null)
const suggestions = ref<Suggestion[]>([])
const statuses = reactive<Record<StepId, StepState>>({
  noise: 'pending',
  belts: 'pending',
  shaperX: 'pending',
  shaperY: 'pending',
  vibrations: 'pending',
  pressure: 'pending',
  done: 'pending',
})
const results = reactive<{
  noise?: NoiseResult
  belts?: BeltComparison
  shaperX?: ShaperAnalysis
  shaperY?: ShaperAnalysis
  vibrations?: VibrationsProfile
}>({})

const step = computed(() => STEPS[idx.value])
const canProceed = computed(() => gate.value?.status === 'passed' || gate.value?.status === 'warn')
const paGcode = PA_TOWER_GCODE
const paSuggestions = recommendPressure()
const paCopied = ref(false)

function stepBg(s: StepState): string {
  if (s === 'passed') return 'bg-brand-lime'
  if (s === 'warn') return 'bg-brand-yellow'
  if (s === 'failed') return 'bg-brand-red text-surface'
  if (s === 'skipped') return 'bg-surface opacity-50'
  return 'bg-surface'
}
function gateBg(status: GateStatus): string {
  if (status === 'passed') return 'bg-brand-lime'
  if (status === 'warn') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
function sugBg(level: Suggestion['level']): string {
  if (level === 'do-now') return 'bg-brand-red text-surface'
  if (level === 'consider') return 'bg-brand-yellow'
  return 'bg-brand-lime'
}
function glyph(s: StepState): string {
  if (s === 'passed') return '✓'
  if (s === 'warn') return '!'
  if (s === 'failed') return '✕'
  if (s === 'skipped') return '–'
  return ''
}

async function run(): Promise<void> {
  const s = step.value
  if (busy.value || (s.motion && !ready.value)) return
  error.value = null
  busy.value = true
  gate.value = null
  try {
    if (s.id === 'noise') {
      const r = await measureNoise()
      results.noise = r
      gate.value = gateNoise(r)
      suggestions.value = recommendNoise(r)
    } else if (s.id === 'belts') {
      const r = await compareBelts()
      results.belts = r
      gate.value = gateBelts(r.belt_a, r.belt_b)
      suggestions.value = recommendBelts(beltVerdict(r.belt_a, r.belt_b))
    } else if (s.id === 'shaperX' || s.id === 'shaperY') {
      const ax = s.id === 'shaperX' ? 'x' : 'y'
      const r = await runLiveTest(ax)
      if (s.id === 'shaperX') results.shaperX = r
      else results.shaperY = r
      gate.value = gateShaper(r)
      suggestions.value = recommendShaper(r)
      emit('analyzed', r) // flows into the parent's byAxis / config / history
    } else if (s.id === 'vibrations') {
      const r = await runVibrationsProfile()
      results.vibrations = r
      gate.value = gateVibrations(r)
      suggestions.value = recommendVibrations(r)
    }
    if (gate.value) statuses[s.id] = gate.value.status
    ready.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('inputShaping.guided.ui.stepFailed')
  } finally {
    busy.value = false
  }
}

function advance(): void {
  idx.value = STEPS.findIndex((s) => s.id === nextStep(step.value.id))
  gate.value = null
  suggestions.value = []
  error.value = null
}
async function copyPa(): Promise<void> {
  try {
    await navigator.clipboard.writeText(paGcode)
    paCopied.value = true
    window.setTimeout(() => (paCopied.value = false), 1500)
  } catch {
    error.value = t('inputShaping.guided.ui.copyFailed')
  }
}
function finishPressure(): void {
  statuses.pressure = 'passed'
  advance()
}
function skip(): void {
  statuses[step.value.id] = 'skipped'
  advance()
}
function review(i: number): void {
  if (statuses[STEPS[i].id] !== 'pending') idx.value = i
}
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <div class="flex items-center justify-between">
      <span class="text-xs font-bold uppercase tracking-wide">{{
        t('inputShaping.guided.ui.title')
      }}</span>
      <button class="nb-btn px-2 py-0.5 text-[11px]" @click="emit('exit')">
        {{ t('inputShaping.guided.ui.exit') }}
      </button>
    </div>

    <!-- Step rail -->
    <div class="flex flex-wrap items-center gap-1">
      <button
        v-for="(s, i) in STEPS"
        :key="s.id"
        class="nb-badge text-[10px]"
        :class="[stepBg(statuses[s.id]), i === idx ? 'ring-2 ring-ink' : '']"
        @click="review(i)"
      >
        {{ glyph(statuses[s.id]) }} {{ tt('inputShaping.guided.steps.' + s.id + '.label') }}
      </button>
    </div>

    <!-- Active step -->
    <div v-if="step.id !== 'done'" class="space-y-1.5 rounded-brutal border-2 border-ink p-2">
      <div class="text-[11px] font-bold">
        {{ tt('inputShaping.guided.steps.' + step.id + '.title') }}
      </div>
      <p class="text-[11px] opacity-70">
        {{ tt('inputShaping.guided.steps.' + step.id + '.why') }}
      </p>

      <!-- Manual: pressure-advance tower. -->
      <div v-if="step.id === 'pressure'" class="space-y-1">
        <pre
          class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
          >{{ paGcode }}</pre
        >
        <div class="flex items-center gap-2">
          <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyPa">
            {{ paCopied ? t('inputShaping.guided.ui.copied') : t('inputShaping.guided.ui.copyPa') }}
          </button>
          <button class="nb-btn bg-brand-lime px-3 py-0.5 text-[11px]" @click="finishPressure">
            {{ t('inputShaping.guided.ui.finish') }}
          </button>
        </div>
        <div
          v-for="(sug, i) in paSuggestions"
          :key="i"
          class="rounded-brutal border-2 border-ink px-2 py-1"
          :class="sugBg(sug.level)"
        >
          <div class="text-[11px] font-bold">{{ sug.title }}</div>
          <p class="text-[10px] leading-snug">{{ sug.why }}</p>
        </div>
      </div>

      <!-- Endpoint step (noise / belts / shaper). -->
      <div v-else class="flex flex-wrap items-center gap-2 text-[11px]">
        <label v-if="step.motion" class="flex items-center gap-1">
          <input v-model="ready" type="checkbox" /> {{ t('inputShaping.guided.ui.motionReady') }}
        </label>
        <button
          class="nb-btn px-2 py-0.5"
          :class="step.motion ? 'bg-brand-red text-surface' : ''"
          :disabled="busy || (step.motion && !ready)"
          @click="run"
        >
          {{
            busy
              ? t('inputShaping.guided.ui.running')
              : statuses[step.id] === 'pending'
                ? t('inputShaping.guided.ui.run')
                : t('inputShaping.guided.ui.rerun')
          }}
        </button>
        <button v-if="step.id === 'belts'" class="nb-btn px-2 py-0.5 text-[11px]" @click="skip">
          {{ t('inputShaping.guided.ui.skipBelts') }}
        </button>
      </div>

      <div v-if="error" role="alert" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

      <VibrationsProfileView
        v-if="step.id === 'vibrations' && results.vibrations"
        :result="results.vibrations"
      />

      <template v-if="gate && step.id !== 'pressure'">
        <div class="flex flex-wrap items-center gap-2">
          <span class="nb-badge text-[11px]" :class="gateBg(gate.status)">{{ gate.headline }}</span>
        </div>
        <div
          v-for="(sug, i) in suggestions"
          :key="i"
          class="rounded-brutal border-2 border-ink px-2 py-1"
          :class="sugBg(sug.level)"
        >
          <div class="text-[11px] font-bold">{{ sug.title }}</div>
          <p class="text-[10px] leading-snug">{{ sug.why }}</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="nb-btn bg-brand-lime px-3 py-0.5 text-[11px]"
            :disabled="!canProceed"
            @click="advance"
          >
            {{ t('inputShaping.guided.ui.nextStep') }}
          </button>
          <button v-if="!canProceed" class="nb-btn px-2 py-0.5 text-[11px]" @click="skip">
            {{ t('inputShaping.guided.ui.skipAnyway') }}
          </button>
        </div>
      </template>
    </div>

    <!-- Summary -->
    <div v-else class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="text-[11px] font-bold">{{ t('inputShaping.guided.ui.complete') }}</div>
      <div class="flex flex-wrap gap-1">
        <span
          v-for="s in STEPS.filter((s) => s.id !== 'done')"
          :key="s.id"
          class="nb-badge text-[10px]"
          :class="stepBg(statuses[s.id])"
        >
          {{ tt('inputShaping.guided.steps.' + s.id + '.label') }} {{ glyph(statuses[s.id]) }}
        </span>
      </div>
      <i18n-t
        keypath="inputShaping.guided.ui.summaryNote"
        tag="p"
        class="text-[10px] opacity-70"
        scope="global"
      >
        <template #code><code>printer.cfg</code></template>
      </i18n-t>
    </div>
  </div>
</template>
