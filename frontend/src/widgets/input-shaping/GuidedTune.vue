<script setup lang="ts">
/** Guided tuning wizard - walks Noise → Belts → Shaper X → Shaper Y → Vibrations → Pressure
 *  with automated pass/fail gates (reusing the existing scorers) and concrete next-step
 *  suggestions. It calls the SAME endpoints as the manual panel and emits each shaper result up
 *  via `analyzed` so the audit/history just work.
 *
 *  Layout: the step rail + the active-step ACTION BAR are pinned at the top, so the buttons never
 *  slide below long results. Each completed stage keeps its own result + chart in the accumulated
 *  "results so far" section (a later Y chart no longer replaces the earlier X chart). The combined
 *  printer.cfg block appears only in the final step.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ConfigApply from '@/components/ui/ConfigApply.vue'
import { copyText } from '@/core/clipboard'

import {
  compareBelts,
  fetchKinematics,
  measureNoise,
  runLiveTest,
  runVibrationsProfile,
  saveConfigToArchive,
} from './api'
import { beltVerdict, buildCompareChart } from './compare'
import { inputShaperConfig } from './config'
import { gradeAnalysis } from './grade'
import {
  type Gate,
  type GateStatus,
  type StepId,
  type StepState,
  gateBelts,
  gateNoise,
  gateShaper,
  gateVibrations,
  nextStep,
  PA_TOWER_GCODE,
  STEPS,
} from './guided'
import {
  clearGuidedSession,
  type GuidedSnapshot,
  loadGuidedSession,
  saveGuidedSession,
} from './guided-store'
import {
  recommendBelts,
  recommendNoise,
  recommendPressure,
  recommendShaper,
  recommendVibrations,
  type Suggestion,
} from './recommend'
import type { BeltComparison, NoiseResult, ShaperAnalysis, VibrationsProfile } from './types'
import ShaperChart from './ShaperChart.vue'
import VibrationsProfileView from './VibrationsProfile.vue'

const emit = defineEmits<{ analyzed: [ShaperAnalysis]; exit: [] }>()

const { t } = useI18n({ useScope: 'global' })
// Step keys are built from the (typed) step id at runtime - use a string-accepting view of t.
const tt = t as unknown as (key: string) => string

const idx = ref(0)
const ready = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
/** True right after a saved in-progress session was restored (drives the "resumed" notice). */
const resumed = ref(false)
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
/** Per-step verdict + suggestions, kept so each accumulated card shows its own result. */
const verdicts = reactive<Partial<Record<StepId, Gate>>>({})
const sugg = reactive<Partial<Record<StepId, Suggestion[]>>>({})
/** Shaper captures the backend auto-archives (so their CSV/chart survive an app restart). */
const archived = reactive<Partial<Record<StepId, boolean>>>({})
/** Which accumulated cards are expanded (defaults to the active step). */
const openCards = reactive<Partial<Record<StepId, boolean>>>({})

const step = computed(() => STEPS[idx.value])
/** Printer kinematics (null until known) - the belts step only applies to CoreXY. */
const kinematics = ref<string | null>(null)
const beltsSupported = computed(
  () => kinematics.value == null || kinematics.value.includes('corexy'),
)

/** The durable slice of the wizard, for persistence (transient busy/error/ready are excluded). */
function snapshot(): GuidedSnapshot {
  return {
    idx: idx.value,
    statuses: { ...statuses },
    results: { ...results },
    verdicts: { ...verdicts },
    sugg: { ...sugg },
    archived: { ...archived },
    openCards: { ...openCards },
    kinematics: kinematics.value,
  }
}

// Persist the in-progress tune on every change so it survives navigating to another widget or an
// accidental refresh. Once the run completes we stop saving (clearGuidedSession, in advance(), has
// already dropped the snapshot) so a finished tune doesn't linger.
watch(
  [idx, statuses, results, verdicts, sugg, archived, openCards, kinematics],
  () => {
    if (statuses.done === 'passed') return
    // Persist only once there's genuine progress (a captured result or a step advanced past the
    // first), so merely opening the wizard doesn't leave a session that shows a spurious
    // "resumed" notice on the next visit.
    const hasProgress =
      idx.value > 0 ||
      !!(results.noise || results.belts || results.shaperX || results.shaperY || results.vibrations)
    if (hasProgress) saveGuidedSession(snapshot())
  },
  { deep: true },
)

function loadKinematics(): void {
  fetchKinematics()
    .then((kin) => {
      kinematics.value = kin
      // Pre-mark the CoreXY-only step on other kinematics so the wizard walks past it.
      if (kin != null && !kin.includes('corexy') && statuses.belts === 'pending')
        statuses.belts = 'skipped'
    })
    .catch(() => (kinematics.value = null))
}

onMounted(() => {
  // Resume an in-progress session if one was saved (widget-switch / refresh). Restore into the
  // reactive objects (not by replacing them) so the accumulated cards + charts re-render.
  const saved = loadGuidedSession()
  if (saved) {
    idx.value = saved.idx
    Object.assign(statuses, saved.statuses)
    Object.assign(results, saved.results)
    Object.assign(verdicts, saved.verdicts)
    Object.assign(sugg, saved.sugg)
    Object.assign(archived, saved.archived)
    Object.assign(openCards, saved.openCards)
    kinematics.value = saved.kinematics
    resumed.value = true
  }
  // Fetch kinematics only if a restore didn't already provide it.
  if (kinematics.value == null) loadKinematics()
})

const canProceed = computed(() => {
  const g = verdicts[step.value.id]
  return g?.status === 'passed' || g?.status === 'warn'
})
const paGcode = PA_TOWER_GCODE
const paSuggestions = recommendPressure()
const paCopied = ref(false)

/** Whether any stage has produced a result yet (drives the "results so far" section). */
const hasResults = computed(
  () =>
    !!(results.noise || results.belts || results.shaperX || results.shaperY || results.vibrations),
)
/** Belt-comparison overlay chart + verdict for the accumulated belts card. */
const beltPlot = computed(() =>
  results.belts ? buildCompareChart(results.belts.belt_a, results.belts.belt_b) : null,
)
const beltV = computed(() =>
  results.belts ? beltVerdict(results.belts.belt_a, results.belts.belt_b) : null,
)
/** Combined [input_shaper] block from the X and Y captures - shown only in the final step. */
const guidedConfig = computed(() => {
  const list = [results.shaperX, results.shaperY].filter(Boolean) as ShaperAnalysis[]
  return list.length ? inputShaperConfig(list) : ''
})
const capturedAxes = computed(() =>
  (['shaperX', 'shaperY'] as const)
    .filter((k) => results[k])
    .map((k) => (k === 'shaperX' ? 'X' : 'Y')),
)
const cfgCopied = ref(false)
const cfgSaved = ref(false)

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
function gradeBg(letter: string): string {
  if (letter === 'A' || letter === 'B') return 'bg-brand-lime'
  if (letter === 'C') return 'bg-brand-yellow'
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
  if (s === 'skipped') return '-'
  return ''
}
function shaperGrade(a: ShaperAnalysis): string {
  return gradeAnalysis(a).letter
}
function isOpen(id: StepId): boolean {
  return openCards[id] ?? id === step.value.id
}
function toggleCard(id: StepId): void {
  openCards[id] = !isOpen(id)
}

async function run(): Promise<void> {
  const s = step.value
  if (busy.value || (s.motion && !ready.value)) return
  error.value = null
  busy.value = true
  try {
    let g: Gate | null = null
    if (s.id === 'noise') {
      const r = await measureNoise()
      results.noise = r
      g = gateNoise(r)
      sugg.noise = recommendNoise(r)
    } else if (s.id === 'belts') {
      if (!beltsSupported.value) {
        statuses.belts = 'skipped'
        advance()
        return
      }
      const r = await compareBelts()
      results.belts = r
      g = gateBelts(r.belt_a, r.belt_b)
      sugg.belts = recommendBelts(beltVerdict(r.belt_a, r.belt_b))
    } else if (s.id === 'shaperX' || s.id === 'shaperY') {
      const ax = s.id === 'shaperX' ? 'x' : 'y'
      const r = await runLiveTest(ax)
      if (s.id === 'shaperX') results.shaperX = r
      else results.shaperY = r
      g = gateShaper(r)
      sugg[s.id] = recommendShaper(r)
      archived[s.id] = true // the backend auto-archives each live capture
      emit('analyzed', r) // flows into the parent's audit / history
    } else if (s.id === 'vibrations') {
      const r = await runVibrationsProfile()
      results.vibrations = r
      g = gateVibrations(r)
      sugg.vibrations = recommendVibrations(r)
    }
    if (g) {
      verdicts[s.id] = g
      statuses[s.id] = g.status
    }
    openCards[s.id] = true // auto-expand the card we just produced
    ready.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('inputShaping.guided.ui.stepFailed')
  } finally {
    busy.value = false
  }
}

function advance(): void {
  idx.value = STEPS.findIndex((s) => s.id === nextStep(step.value.id))
  if (step.value.id === 'belts' && !beltsSupported.value) {
    statuses.belts = 'skipped'
    idx.value = STEPS.findIndex((s) => s.id === nextStep('belts'))
  }
  error.value = null
  // Reaching the final step completes the run: mark its rail badge, drop the saved session (the
  // tune is finished, per "keep it until done"), and auto-save the config.
  if (step.value.id === 'done') {
    statuses.done = 'passed'
    clearGuidedSession()
    void saveGuidedConfig(true)
  }
}

async function copyPa(): Promise<void> {
  if (await copyText(paGcode)) {
    paCopied.value = true
    window.setTimeout(() => (paCopied.value = false), 1500)
  } else {
    error.value = t('inputShaping.guided.ui.copyFailed')
  }
}
async function copyConfig(): Promise<void> {
  if (!guidedConfig.value) return
  if (await copyText(guidedConfig.value)) {
    cfgCopied.value = true
    window.setTimeout(() => (cfgCopied.value = false), 1500)
  } else {
    error.value = t('inputShaping.guided.ui.copyFailed')
  }
}
/** Files the combined config into the on-host archive. Auto-called on completion (best-effort),
 *  and re-runnable from the Archive button. */
async function saveGuidedConfig(auto = false): Promise<void> {
  if (!guidedConfig.value) return
  try {
    const primary = results.shaperX ?? results.shaperY
    await saveConfigToArchive(guidedConfig.value, null, {
      shaper: primary?.recommended_shaper ?? null,
      freq: primary?.recommended_freq ?? null,
    })
    cfgSaved.value = true
  } catch (e) {
    // The archive lives on the printer host - off-host the auto-save just no-ops.
    if (!auto) error.value = e instanceof Error ? e.message : t('inputShaping.guided.ui.stepFailed')
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

    <!-- Shown once when a saved in-progress tune was restored (survives widget-switch / refresh).
         Click to dismiss. -->
    <button
      v-if="resumed"
      class="nb-badge flex items-center gap-1 bg-brand-cyan text-[10px]"
      @click="resumed = false"
    >
      <span aria-hidden="true">↻</span> {{ t('inputShaping.guided.ui.resumed') }}
    </button>

    <!-- Pinned control zone: the step rail + the active-step ACTION BAR stay at the top, so the
         buttons never slide below the (possibly tall) results. -->
    <div class="sticky top-0 z-10 -mx-2 space-y-2 border-b-2 border-ink bg-paper px-2 pb-2">
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

      <!-- Active step: title, why, and the action bar (run / next / skip, or the pressure tools). -->
      <div v-if="step.id !== 'done'" class="space-y-1.5">
        <div class="text-[11px] font-bold">
          {{ tt('inputShaping.guided.steps.' + step.id + '.title') }}
        </div>
        <p class="text-[11px] opacity-70">
          {{ tt('inputShaping.guided.steps.' + step.id + '.why') }}
        </p>

        <p v-if="step.id === 'belts' && !beltsSupported" class="text-[11px] text-brand-red">
          {{ t('inputShaping.guided.ui.beltsNotApplicable', { kin: kinematics }) }}
        </p>

        <!-- Manual pressure-advance tower: the g-code to run by hand. -->
        <pre
          v-if="step.id === 'pressure'"
          class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
          >{{ paGcode }}</pre>

        <!-- Action bar -->
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          <template v-if="step.id === 'pressure'">
            <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyPa">
              {{
                paCopied ? t('inputShaping.guided.ui.copied') : t('inputShaping.guided.ui.copyPa')
              }}
            </button>
            <button class="nb-btn bg-brand-lime px-3 py-0.5 text-[11px]" @click="finishPressure">
              {{ t('inputShaping.guided.ui.finish') }}
            </button>
          </template>
          <template v-else>
            <label v-if="step.motion" class="flex items-center gap-1">
              <input v-model="ready" type="checkbox" />
              {{ t('inputShaping.guided.ui.motionReady') }}
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
            <button
              v-if="verdicts[step.id]"
              class="nb-btn bg-brand-lime px-3 py-0.5 text-[11px]"
              :disabled="!canProceed"
              @click="advance"
            >
              {{ t('inputShaping.guided.ui.nextStep') }}
            </button>
            <button
              v-if="step.id === 'belts' && !verdicts.belts"
              class="nb-btn px-2 py-0.5 text-[11px]"
              @click="skip"
            >
              {{ t('inputShaping.guided.ui.skipBelts') }}
            </button>
            <button
              v-if="verdicts[step.id] && !canProceed"
              class="nb-btn px-2 py-0.5 text-[11px]"
              @click="skip"
            >
              {{ t('inputShaping.guided.ui.skipAnyway') }}
            </button>
          </template>
          <!-- Current-step verdict, for an immediate go / no-go without scrolling to the card. -->
          <span
            v-if="verdicts[step.id]"
            class="nb-badge text-[11px]"
            :class="gateBg(verdicts[step.id]!.status)"
            >{{ verdicts[step.id]!.headline }}</span
          >
        </div>

        <!-- Pressure is a manual instruction step - its tips live here (it has no measured card). -->
        <div
          v-for="(s, i) in step.id === 'pressure' ? paSuggestions : []"
          :key="i"
          class="rounded-brutal border-2 border-ink px-2 py-1"
          :class="sugBg(s.level)"
        >
          <div class="text-[11px] font-bold">{{ s.title }}</div>
          <p class="text-[10px] leading-snug">{{ s.why }}</p>
        </div>

        <div v-if="error" role="alert" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
      </div>
    </div>

    <!-- Results so far: each completed stage keeps its own result + chart, stacked (collapsible). -->
    <div v-if="hasResults" class="space-y-1.5">
      <div class="text-[10px] font-bold uppercase tracking-wide opacity-60">
        {{ t('inputShaping.guided.ui.resultsSoFar') }}
      </div>

      <!-- Noise -->
      <div v-if="results.noise" class="rounded-brutal border-2 border-ink">
        <button
          class="flex w-full items-center gap-2 px-2 py-1.5 text-start"
          @click="toggleCard('noise')"
        >
          <span class="nb-badge text-[10px]" :class="stepBg(statuses.noise)">{{
            glyph(statuses.noise)
          }}</span>
          <span class="text-[11px] font-bold">{{
            tt('inputShaping.guided.steps.noise.label')
          }}</span>
          <span
            v-if="verdicts.noise"
            class="nb-badge text-[10px]"
            :class="gateBg(verdicts.noise.status)"
            >{{ verdicts.noise.headline }}</span
          >
          <span class="flex-1"></span>
          <span class="font-mono text-[11px]">{{ isOpen('noise') ? '▾' : '▸' }}</span>
        </button>
        <div v-show="isOpen('noise')" class="space-y-1.5 border-t-2 border-ink p-2">
          <div
            v-for="(s, i) in sugg.noise ?? []"
            :key="i"
            class="rounded-brutal border-2 border-ink px-2 py-1"
            :class="sugBg(s.level)"
          >
            <div class="text-[11px] font-bold">{{ s.title }}</div>
            <p class="text-[10px] leading-snug">{{ s.why }}</p>
          </div>
        </div>
      </div>

      <!-- Belts -->
      <div v-if="results.belts" class="rounded-brutal border-2 border-ink">
        <button
          class="flex w-full items-center gap-2 px-2 py-1.5 text-start"
          @click="toggleCard('belts')"
        >
          <span class="nb-badge text-[10px]" :class="stepBg(statuses.belts)">{{
            glyph(statuses.belts)
          }}</span>
          <span class="text-[11px] font-bold">{{
            tt('inputShaping.guided.steps.belts.label')
          }}</span>
          <span
            v-if="verdicts.belts"
            class="nb-badge text-[10px]"
            :class="gateBg(verdicts.belts.status)"
            >{{ verdicts.belts.headline }}</span
          >
          <span class="flex-1"></span>
          <span class="font-mono text-[11px]">{{ isOpen('belts') ? '▾' : '▸' }}</span>
        </button>
        <div v-show="isOpen('belts')" class="space-y-1.5 border-t-2 border-ink p-2">
          <div v-if="beltV" class="flex flex-wrap gap-1.5">
            <span class="nb-badge bg-surface font-mono text-[10px]"
              >{{ t('inputShaping.guided.ui.beltA') }} {{ beltV.peakA.toFixed(0) }} Hz</span
            >
            <span class="nb-badge bg-surface font-mono text-[10px]"
              >{{ t('inputShaping.guided.ui.beltB') }} {{ beltV.peakB.toFixed(0) }} Hz</span
            >
          </div>
          <svg
            v-if="beltPlot"
            :viewBox="`0 0 ${beltPlot.width} ${beltPlot.height}`"
            class="w-full rounded-brutal border-2 border-ink bg-surface"
            role="img"
            :aria-label="t('inputShaping.compareView.chartAriaLabel')"
          >
            <line
              v-for="tick in beltPlot.xTicks"
              :key="'g' + tick.label"
              :x1="tick.x"
              :x2="tick.x"
              :y1="6"
              :y2="beltPlot.height - 12"
              class="stroke-ink"
              stroke-opacity="0.12"
              stroke-width="0.5"
            />
            <polyline
              :points="beltPlot.a.points"
              fill="none"
              :stroke="beltPlot.a.color"
              stroke-width="1"
            />
            <polyline
              :points="beltPlot.b.points"
              fill="none"
              :stroke="beltPlot.b.color"
              stroke-width="1"
              stroke-dasharray="2 2"
            />
            <text
              v-for="tick in beltPlot.xTicks"
              :key="'t' + tick.label"
              :x="tick.x"
              :y="beltPlot.height - 2"
              font-size="6"
              class="fill-ink"
              fill-opacity="0.6"
              text-anchor="middle"
            >
              {{ tick.label }}
            </text>
          </svg>
          <div class="flex flex-wrap gap-x-3 font-mono text-[10px]">
            <span class="flex items-center gap-1">
              <span
                class="inline-block h-2 w-3 rounded-xs"
                :style="{ background: beltPlot?.a.color }"
              />
              {{ t('inputShaping.guided.ui.beltA') }}
            </span>
            <span class="flex items-center gap-1">
              <span
                class="inline-block h-0 w-3 border-t-2 border-dashed"
                :style="{ borderColor: beltPlot?.b.color }"
              />
              {{ t('inputShaping.guided.ui.beltB') }}
            </span>
          </div>
          <div
            v-for="(s, i) in sugg.belts ?? []"
            :key="i"
            class="rounded-brutal border-2 border-ink px-2 py-1"
            :class="sugBg(s.level)"
          >
            <div class="text-[11px] font-bold">{{ s.title }}</div>
            <p class="text-[10px] leading-snug">{{ s.why }}</p>
          </div>
        </div>
      </div>

      <!-- Shaper X / Shaper Y -->
      <div
        v-for="ax in (['shaperX', 'shaperY'] as const).filter((k) => results[k])"
        :key="ax"
        class="rounded-brutal border-2 border-ink"
      >
        <button
          class="flex w-full items-center gap-2 px-2 py-1.5 text-start"
          @click="toggleCard(ax)"
        >
          <span class="nb-badge text-[10px]" :class="stepBg(statuses[ax])">{{
            glyph(statuses[ax])
          }}</span>
          <span class="text-[11px] font-bold">{{
            tt('inputShaping.guided.steps.' + ax + '.label')
          }}</span>
          <span
            v-if="verdicts[ax]"
            class="nb-badge text-[10px]"
            :class="gateBg(verdicts[ax]!.status)"
            >{{ verdicts[ax]!.headline }}</span
          >
          <span v-if="archived[ax]" class="nb-badge bg-brand-lime text-[10px]">{{
            t('inputShaping.guided.ui.archived')
          }}</span>
          <span class="flex-1"></span>
          <span class="font-mono text-[11px]">{{ isOpen(ax) ? '▾' : '▸' }}</span>
        </button>
        <div v-show="isOpen(ax)" class="space-y-1.5 border-t-2 border-ink p-2">
          <div v-if="results[ax]!.recommended_shaper" class="flex flex-wrap items-center gap-2">
            <span class="nb-badge text-[10px]" :class="gradeBg(shaperGrade(results[ax]!))">{{
              shaperGrade(results[ax]!)
            }}</span>
            <span class="font-mono text-[11px] font-bold">{{
              results[ax]!.recommended_shaper!.toUpperCase()
            }}</span>
            <span class="font-mono text-[11px]">{{
              t('inputShaping.widget.recFreq', { v: results[ax]!.recommended_freq?.toFixed(1) })
            }}</span>
          </div>
          <ShaperChart :analysis="results[ax]!" />
          <div
            v-for="(s, i) in sugg[ax] ?? []"
            :key="i"
            class="rounded-brutal border-2 border-ink px-2 py-1"
            :class="sugBg(s.level)"
          >
            <div class="text-[11px] font-bold">{{ s.title }}</div>
            <p class="text-[10px] leading-snug">{{ s.why }}</p>
          </div>
        </div>
      </div>

      <!-- Vibrations -->
      <div v-if="results.vibrations" class="rounded-brutal border-2 border-ink">
        <button
          class="flex w-full items-center gap-2 px-2 py-1.5 text-start"
          @click="toggleCard('vibrations')"
        >
          <span class="nb-badge text-[10px]" :class="stepBg(statuses.vibrations)">{{
            glyph(statuses.vibrations)
          }}</span>
          <span class="text-[11px] font-bold">{{
            tt('inputShaping.guided.steps.vibrations.label')
          }}</span>
          <span
            v-if="verdicts.vibrations"
            class="nb-badge text-[10px]"
            :class="gateBg(verdicts.vibrations.status)"
            >{{ verdicts.vibrations.headline }}</span
          >
          <span class="flex-1"></span>
          <span class="font-mono text-[11px]">{{ isOpen('vibrations') ? '▾' : '▸' }}</span>
        </button>
        <div v-show="isOpen('vibrations')" class="space-y-1.5 border-t-2 border-ink p-2">
          <VibrationsProfileView :result="results.vibrations" />
          <div
            v-for="(s, i) in sugg.vibrations ?? []"
            :key="i"
            class="rounded-brutal border-2 border-ink px-2 py-1"
            :class="sugBg(s.level)"
          >
            <div class="text-[11px] font-bold">{{ s.title }}</div>
            <p class="text-[10px] leading-snug">{{ s.why }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Final step: completion summary + the combined printer.cfg block (only shown here). -->
    <div v-if="step.id === 'done'" class="space-y-2 rounded-brutal border-2 border-ink p-2">
      <div class="text-[11px] font-bold">{{ t('inputShaping.guided.ui.complete') }}</div>

      <div v-if="guidedConfig" class="space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-bold uppercase tracking-wide">{{
            t('inputShaping.widget.printerCfg')
          }}</span>
          <span v-for="a in capturedAxes" :key="a" class="nb-badge bg-brand-cyan text-[10px]">{{
            a
          }}</span>
          <span class="flex-1"></span>
          <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyConfig">
            {{ cfgCopied ? t('inputShaping.widget.copied') : t('inputShaping.widget.copy') }}
          </button>
          <button class="nb-btn px-2 py-0.5 text-[11px]" @click="saveGuidedConfig(false)">
            {{ cfgSaved ? t('inputShaping.widget.saved') : t('inputShaping.widget.archive') }}
          </button>
        </div>
        <pre
          class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
          >{{ guidedConfig }}</pre>
        <p v-if="cfgSaved" class="text-[10px] text-brand-lime">
          {{ t('inputShaping.guided.ui.autoSaved') }}
        </p>
        <i18n-t
          keypath="inputShaping.widget.pasteHint"
          tag="p"
          scope="global"
          class="text-[10px] italic opacity-50"
        >
          <template #cfg><code>printer.cfg</code></template>
        </i18n-t>

        <!-- The last mile: write the block straight into the config, behind the shared gate. -->
        <details class="nb-card bg-surface p-2">
          <summary class="cursor-pointer text-xs font-bold">{{ t('configApply.title') }}</summary>
          <div class="mt-2"><ConfigApply :block="guidedConfig" /></div>
        </details>
      </div>

      <i18n-t
        keypath="inputShaping.guided.ui.summaryNote"
        tag="p"
        class="text-[10px] opacity-70"
        scope="global"
      >
        <template #code><code>printer.cfg</code></template>
      </i18n-t>

      <div v-if="error" role="alert" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
    </div>
  </div>
</template>
