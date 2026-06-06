<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  compareBelts,
  measureNoise,
  runAxesMap,
  runLiveTest,
  runStaticExcitation,
  runVibrationsProfile,
} from './api'
import {
  type AuditRecord,
  buildAxesMapRecord,
  buildBeltsRecord,
  buildNoiseRecord,
  buildSustainRecord,
  buildVibrationsRecord,
} from './audit'
import { buildAxesVelocityChart } from './axesChart'
import { angleClass, axesMapConfig, mappingArrow, matchVerdict, statusBg } from './axesMap'
import { beltVerdict, buildCompareChart } from './compare'
import { buildEnergyTimeline, buildSpectrogram } from './spectrogram-chart'
import type {
  AxesMapResult,
  BeltComparison,
  NoiseResult,
  ShaperAnalysis,
  StaticExcitationResult,
  VibrationsProfile as VibrationsProfileResult,
} from './types'
import HelpNote from './HelpNote.vue'
import VibrationsProfile from './VibrationsProfile.vue'

const emit = defineEmits<{
  analyzed: [ShaperAnalysis]
  recorded: [Omit<AuditRecord, 'id' | 'source'>]
}>()

const { t } = useI18n({ useScope: 'global' })

const error = ref<string | null>(null)
const liveAxis = ref<'x' | 'y'>('x')
const liveReady = ref(false)
const liveBusy = ref(false)
// Each motion tool has its OWN confirm checkbox, so ticking "ready" for one can't
// accidentally arm a different (and possibly much larger) motion.
const beltsReady = ref(false)
const axesReady = ref(false)
const noise = ref<NoiseResult | null>(null)
const noiseBusy = ref(false)
const belts = ref<BeltComparison | null>(null)
const beltsBusy = ref(false)
const axesMapResult = ref<AxesMapResult | null>(null)
const axesBusy = ref(false)
const axesCopied = ref(false)
const staticResult = ref<StaticExcitationResult | null>(null)
const staticBusy = ref(false)
const staticReady = ref(false)
const staticAxis = ref<'x' | 'y'>('x')
const staticFreq = ref('50')
const staticDuration = ref('15')
const vibResult = ref<VibrationsProfileResult | null>(null)
const vibBusy = ref(false)
const vibReady = ref(false)
const vibMaxSpeed = ref('200')
const vibIncrement = ref('10')

const beltChart = computed(() =>
  belts.value ? buildCompareChart(belts.value.belt_a, belts.value.belt_b) : null,
)
const beltJudge = computed(() =>
  belts.value ? beltVerdict(belts.value.belt_a, belts.value.belt_b) : null,
)
const axesChart = computed(() =>
  axesMapResult.value ? buildAxesVelocityChart(axesMapResult.value.velocity_series) : null,
)
const specChart = computed(() => (staticResult.value ? buildSpectrogram(staticResult.value) : null))
const energyChart = computed(() =>
  staticResult.value ? buildEnergyTimeline(staticResult.value) : null,
)
/** Any toolhead-moving action in flight (the gated buttons share this). */
const motionBusy = computed(
  () => liveBusy.value || beltsBusy.value || axesBusy.value || staticBusy.value || vibBusy.value,
)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'
const numClass = `${inputClass} w-14 font-mono`

function noiseClass(grade: NoiseResult['grade']): string {
  if (grade === 'good') return 'bg-brand-lime'
  if (grade === 'elevated') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
function noiseVerdict(grade: NoiseResult['grade']): string {
  if (grade === 'good') return t('inputShaping.fromPrinter.noiseVerdictQuiet')
  if (grade === 'elevated') return t('inputShaping.fromPrinter.noiseVerdictElevated')
  return t('inputShaping.fromPrinter.noiseVerdictTooNoisy')
}

function msg(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

async function checkNoise(): Promise<void> {
  if (noiseBusy.value) return
  error.value = null
  noiseBusy.value = true
  try {
    const r = await measureNoise()
    noise.value = r
    emit('recorded', buildNoiseRecord(r))
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errNoiseCheck'))
  } finally {
    noiseBusy.value = false
  }
}

async function live(): Promise<void> {
  if (liveBusy.value || !liveReady.value) return
  error.value = null
  liveBusy.value = true
  try {
    const result = await runLiveTest(liveAxis.value)
    liveReady.value = false
    emit('analyzed', result)
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errLiveTest'))
  } finally {
    liveBusy.value = false
  }
}

async function runBelts(): Promise<void> {
  if (beltsBusy.value || !beltsReady.value) return
  error.value = null
  beltsBusy.value = true
  try {
    const r = await compareBelts()
    belts.value = r
    beltsReady.value = false
    emit('recorded', buildBeltsRecord(r))
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errBeltComparison'))
  } finally {
    beltsBusy.value = false
  }
}

async function runAxes(): Promise<void> {
  if (axesBusy.value || !axesReady.value) return
  error.value = null
  axesBusy.value = true
  try {
    const r = await runAxesMap()
    axesMapResult.value = r
    axesReady.value = false
    emit('recorded', buildAxesMapRecord(r))
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errAxesMapDetection'))
  } finally {
    axesBusy.value = false
  }
}

async function copyAxesMap(): Promise<void> {
  if (!axesMapResult.value) return
  try {
    await navigator.clipboard.writeText(axesMapConfig(axesMapResult.value))
    axesCopied.value = true
    window.setTimeout(() => (axesCopied.value = false), 1500)
  } catch {
    error.value = t('inputShaping.fromPrinter.errCopyFailed')
  }
}

async function runStatic(): Promise<void> {
  if (staticBusy.value || !staticReady.value) return
  error.value = null
  staticBusy.value = true
  try {
    const r = await runStaticExcitation(
      staticAxis.value,
      Number(staticFreq.value) || 50,
      Number(staticDuration.value) || 15,
    )
    staticResult.value = r
    staticReady.value = false
    emit('recorded', buildSustainRecord(r))
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errSustainTest'))
  } finally {
    staticBusy.value = false
  }
}

// (host-file import + the file list now live in the Analyze tab's CSV source chooser)

async function runVib(): Promise<void> {
  if (vibBusy.value || !vibReady.value) return
  error.value = null
  vibBusy.value = true
  try {
    const r = await runVibrationsProfile({
      maxSpeed: Number(vibMaxSpeed.value) || 200,
      speedIncrement: Number(vibIncrement.value) || 10,
    })
    vibResult.value = r
    vibReady.value = false
    emit('recorded', buildVibrationsRecord(r))
  } catch (e) {
    error.value = msg(e, t('inputShaping.fromPrinter.errVibrationsProfile'))
  } finally {
    vibBusy.value = false
  }
}
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <span class="text-xs font-bold uppercase tracking-wide">{{
      t('inputShaping.fromPrinter.liveTools')
    }}</span>
    <i18n-t
      keypath="inputShaping.fromPrinter.intro"
      tag="p"
      scope="global"
      class="font-mono text-[10px] opacity-60"
    >
      <template #duration
        ><strong>{{ t('inputShaping.fromPrinter.introDuration') }}</strong></template
      >
    </i18n-t>

    <!-- Accelerometer noise pre-check — motion-free, validates the sensor mount. -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.noiseTitle') }}</span>
        <button class="nb-btn px-2 py-0.5" :disabled="noiseBusy" @click="checkNoise">
          {{
            noiseBusy
              ? t('inputShaping.fromPrinter.noiseBtnBusy')
              : t('inputShaping.fromPrinter.noiseBtn')
          }}
        </button>
        <span class="opacity-60">{{ t('inputShaping.fromPrinter.noiseHint') }}</span>
      </div>
      <HelpNote topic="noise" />
      <div v-if="noise" class="space-y-0.5">
        <div class="flex flex-wrap items-center gap-2">
          <span class="nb-badge" :class="noiseClass(noise.grade)">{{
            noiseVerdict(noise.grade)
          }}</span>
          <span class="font-mono text-[10px] opacity-60">{{
            t('inputShaping.fromPrinter.noiseMaxNormal', {
              max: noise.max_noise.toFixed(1),
              threshold: noise.threshold,
            })
          }}</span>
        </div>
        <div v-for="c in noise.chips" :key="c.label" class="font-mono text-[10px] opacity-70">
          {{
            t('inputShaping.fromPrinter.noiseChip', {
              label: c.label,
              x: c.x.toFixed(1),
              y: c.y.toFixed(1),
              z: c.z.toFixed(1),
            })
          }}
        </div>
      </div>
    </div>

    <!-- Each on-printer motion tool is its own panel with its OWN confirm, so arming one
         motion can't trigger another (consistent with the Sustain / Vibrations panels). -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.liveTitle') }}</span>
        <select v-model="liveAxis" :class="inputClass">
          <option value="x">{{ t('inputShaping.fromPrinter.axisX') }}</option>
          <option value="y">{{ t('inputShaping.fromPrinter.axisY') }}</option>
        </select>
        <label class="flex items-center gap-1">
          <input v-model="liveReady" type="checkbox" />
          {{ t('inputShaping.fromPrinter.confirmMoves') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || motionBusy"
          @click="live"
        >
          {{
            liveBusy
              ? t('inputShaping.fromPrinter.liveBtnBusy')
              : t('inputShaping.fromPrinter.liveBtn')
          }}
        </button>
      </div>
      <i18n-t
        keypath="inputShaping.fromPrinter.liveDesc"
        tag="p"
        scope="global"
        class="font-mono text-[10px] opacity-60"
      >
        <template #section><code>[resonance_tester]</code></template>
      </i18n-t>
    </div>

    <!-- Compare belts (CoreXY) — its own confirm. -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.beltsTitle') }}</span>
        <label class="flex items-center gap-1">
          <input v-model="beltsReady" type="checkbox" />
          {{ t('inputShaping.fromPrinter.confirmMoves') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!beltsReady || motionBusy"
          :title="t('inputShaping.fromPrinter.beltsBtnTitle')"
          @click="runBelts"
        >
          {{
            beltsBusy
              ? t('inputShaping.fromPrinter.beltsBtnBusy')
              : t('inputShaping.fromPrinter.beltsBtn')
          }}
        </button>
      </div>
      <p class="font-mono text-[10px] opacity-60">
        {{ t('inputShaping.fromPrinter.beltsDesc') }}
      </p>
      <HelpNote topic="belts" />
    </div>

    <!-- Axes map — its own confirm. -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.axesTitle') }}</span>
        <label class="flex items-center gap-1">
          <input v-model="axesReady" type="checkbox" />
          {{ t('inputShaping.fromPrinter.confirmMoves') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!axesReady || motionBusy"
          :title="t('inputShaping.fromPrinter.axesBtnTitle')"
          @click="runAxes"
        >
          {{
            axesBusy
              ? t('inputShaping.fromPrinter.axesBtnBusy')
              : t('inputShaping.fromPrinter.axesBtn')
          }}
        </button>
      </div>
      <p class="font-mono text-[10px] opacity-60">
        {{ t('inputShaping.fromPrinter.axesDesc') }}
      </p>
      <HelpNote topic="axesMap" />
    </div>

    <!-- Belt comparison (CoreXY): the two belt-direction responses overlaid. -->
    <div
      v-if="belts && beltChart && beltJudge"
      class="space-y-1 rounded-brutal border-2 border-ink p-2"
    >
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] font-bold uppercase tracking-wide">{{
          t('inputShaping.fromPrinter.beltResultTitle')
        }}</span>
        <span
          class="nb-badge"
          :class="beltJudge.level === 'good' ? 'bg-brand-lime' : 'bg-brand-yellow'"
          >{{ beltJudge.matched ? '✅' : '⚠' }} {{ beltJudge.title }}</span
        >
        <span class="font-mono text-[10px] opacity-60">{{
          t('inputShaping.fromPrinter.beltPeaks', {
            a: beltJudge.peakA.toFixed(1),
            b: beltJudge.peakB.toFixed(1),
            diff: beltJudge.diffPct.toFixed(0),
          })
        }}</span>
      </div>
      <svg
        :viewBox="`0 0 ${beltChart.width} ${beltChart.height}`"
        class="w-full rounded-brutal border-2 border-ink bg-paper"
        role="img"
        :aria-label="t('inputShaping.fromPrinter.beltChartLabel')"
      >
        <line
          v-for="tick in beltChart.xTicks"
          :key="'bg' + tick.label"
          :x1="tick.x"
          :x2="tick.x"
          :y1="6"
          :y2="beltChart.height - 12"
          stroke="#111111"
          stroke-opacity="0.12"
          stroke-width="0.5"
        />
        <polyline
          :points="beltChart.a.points"
          fill="none"
          :stroke="beltChart.a.color"
          stroke-width="1"
        />
        <polyline
          :points="beltChart.b.points"
          fill="none"
          :stroke="beltChart.b.color"
          stroke-width="1"
          stroke-dasharray="2 2"
        />
        <text
          v-for="tick in beltChart.xTicks"
          :key="'bt' + tick.label"
          :x="tick.x"
          :y="beltChart.height - 2"
          font-size="6"
          fill="#111111"
          fill-opacity="0.6"
          text-anchor="middle"
        >
          {{ tick.label }}
        </text>
      </svg>
      <p class="text-[10px] opacity-70">{{ beltJudge.advice }}</p>
      <div class="flex gap-3 font-mono text-[10px]">
        <span class="flex items-center gap-1"
          ><span class="inline-block h-0 w-3 border-t-2" style="border-color: #5b8cff" />
          {{ t('inputShaping.fromPrinter.beltLegendA') }}</span
        >
        <span class="flex items-center gap-1"
          ><span class="inline-block h-0 w-3 border-t-2" style="border-color: #ff5247" />
          {{ t('inputShaping.fromPrinter.beltLegendB') }}</span
        >
      </div>
    </div>

    <!-- Axes-map detection: orientation + the paste-ready axes_map. -->
    <div v-if="axesMapResult && axesChart" class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] font-bold uppercase tracking-wide">{{
          t('inputShaping.fromPrinter.axesResultTitle')
        }}</span>
        <span class="nb-badge font-mono text-xs" :class="statusBg(axesMapResult.status)">{{
          axesMapResult.axes_map
        }}</span>
        <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyAxesMap">
          {{
            axesCopied ? t('inputShaping.fromPrinter.copied') : t('inputShaping.fromPrinter.copy')
          }}
        </button>
      </div>
      <p class="text-[10px] opacity-70">{{ matchVerdict(axesMapResult) }}</p>
      <div class="flex flex-wrap gap-1.5 font-mono text-[10px]">
        <span
          v-for="m in axesMapResult.mappings"
          :key="m.machine_axis"
          class="nb-badge"
          :class="m.extrapolated ? 'bg-surface opacity-60' : angleClass(m.angle_error)"
        >
          {{ mappingArrow(m)
          }}{{
            m.extrapolated
              ? t('inputShaping.fromPrinter.mappingVirtual')
              : t('inputShaping.fromPrinter.mappingAngle', { angle: m.angle_error.toFixed(0) })
          }}
        </span>
      </div>
      <svg
        :viewBox="`0 0 ${axesChart.width} ${axesChart.height}`"
        class="w-full rounded-brutal border-2 border-ink bg-paper"
        role="img"
        :aria-label="t('inputShaping.fromPrinter.axesChartLabel')"
      >
        <line
          :x1="4"
          :x2="axesChart.width - 4"
          :y1="axesChart.zeroY"
          :y2="axesChart.zeroY"
          stroke="#111111"
          stroke-opacity="0.2"
          stroke-width="0.5"
        />
        <line
          v-for="(b, i) in axesChart.boundaries"
          :key="'ab' + i"
          :x1="b"
          :x2="b"
          :y1="6"
          :y2="axesChart.height - 12"
          stroke="#111111"
          stroke-opacity="0.15"
          stroke-width="0.5"
          stroke-dasharray="2 2"
        />
        <template v-for="(z, i) in axesChart.zones" :key="'z' + i">
          <polyline :points="z.vx" fill="none" :stroke="axesChart.colors.x" stroke-width="0.8" />
          <polyline :points="z.vy" fill="none" :stroke="axesChart.colors.y" stroke-width="0.8" />
          <polyline :points="z.vz" fill="none" :stroke="axesChart.colors.z" stroke-width="0.8" />
          <text
            :x="z.centerX"
            :y="11"
            font-size="6"
            font-weight="bold"
            fill="#111111"
            text-anchor="middle"
          >
            {{ z.axis }} → {{ z.detected }}
          </text>
          <text
            :x="z.centerX"
            :y="axesChart.height - 2"
            font-size="5.5"
            fill="#111111"
            fill-opacity="0.6"
            text-anchor="middle"
          >
            {{
              z.extrapolated
                ? t('inputShaping.fromPrinter.zoneVirtual')
                : t('inputShaping.fromPrinter.zonePct', { pct: (z.confidence * 100).toFixed(0) })
            }}
          </text>
        </template>
      </svg>
      <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] opacity-70">
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #ff5247" />{{
            t('inputShaping.fromPrinter.legendAccelX')
          }}</span
        >
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #5b8cff" />{{
            t('inputShaping.fromPrinter.legendY')
          }}</span
        >
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #00e0c6" />{{
            t('inputShaping.fromPrinter.legendZ')
          }}</span
        >
        <span>{{
          t('inputShaping.fromPrinter.tilt', {
            x: axesMapResult.euler.x?.toFixed(1),
            y: axesMapResult.euler.y?.toFixed(1),
            z: axesMapResult.euler.z?.toFixed(1),
          })
        }}</span>
        <span>{{
          t('inputShaping.fromPrinter.gravity', { v: axesMapResult.gravity.toFixed(2) })
        }}</span>
        <span :class="axesMapResult.noise_grade === 'ok' ? '' : 'text-brand-red'">{{
          t('inputShaping.fromPrinter.noiseValue', { v: axesMapResult.noise.toFixed(0) })
        }}</span>
      </div>
      <p v-if="axesMapResult.messages.length" class="text-[10px] opacity-60">
        {{ axesMapResult.messages.join(' · ') }}
      </p>
    </div>

    <!-- Sustain frequency: hold a frequency in place to find what rattles by hand. -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.sustainTitle') }}</span>
        <select v-model="staticAxis" :class="inputClass">
          <option value="x">{{ t('inputShaping.fromPrinter.sustainAxisX') }}</option>
          <option value="y">{{ t('inputShaping.fromPrinter.sustainAxisY') }}</option>
        </select>
        <label class="flex items-center gap-1"
          >{{ t('inputShaping.fromPrinter.sustainHz') }}
          <input v-model="staticFreq" :class="numClass"
        /></label>
        <label class="flex items-center gap-1"
          >{{ t('inputShaping.fromPrinter.sustainSec') }}
          <input v-model="staticDuration" :class="numClass"
        /></label>
        <label class="flex items-center gap-1">
          <input v-model="staticReady" type="checkbox" />
          {{ t('inputShaping.fromPrinter.confirmMoves') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!staticReady || motionBusy"
          @click="runStatic"
        >
          {{
            staticBusy
              ? t('inputShaping.fromPrinter.sustainBtnBusy')
              : t('inputShaping.fromPrinter.sustainBtn')
          }}
        </button>
      </div>
      <p class="font-mono text-[10px] opacity-60">
        {{ t('inputShaping.fromPrinter.sustainDesc') }}
      </p>
      <HelpNote topic="sustain" />
      <div v-if="staticResult && specChart && energyChart" class="space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="nb-badge"
            :class="staticResult.dominant_ok ? 'bg-brand-lime' : 'bg-brand-yellow'"
            >{{
              staticResult.dominant_ok
                ? t('inputShaping.fromPrinter.sustainHolding')
                : t('inputShaping.fromPrinter.sustainOffTarget')
            }}</span
          >
          <span class="font-mono text-[10px] opacity-60">{{
            t('inputShaping.fromPrinter.sustainPeak', {
              freq: staticResult.dominant_freq.toFixed(0),
              pct: staticResult.excited_band_pct.toFixed(0),
            })
          }}</span>
        </div>
        <p class="text-[10px] opacity-80">{{ staticResult.verdict }}</p>
        <svg
          :viewBox="`0 0 ${specChart.width} ${specChart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          :aria-label="t('inputShaping.fromPrinter.specChartLabel')"
        >
          <rect
            v-for="(c, i) in specChart.cells"
            :key="'c' + i"
            :x="c.x"
            :y="c.y"
            :width="c.w"
            :height="c.h"
            :fill="c.fill"
          />
          <line
            v-if="specChart.guideX != null"
            :x1="specChart.guideX"
            :x2="specChart.guideX"
            :y1="6"
            :y2="specChart.height - 12"
            stroke="#111111"
            stroke-width="0.7"
            stroke-dasharray="2 1.5"
          />
          <text
            v-for="tick in specChart.freqTicks"
            :key="'ft' + tick.label"
            :x="tick.x"
            :y="specChart.height - 2"
            font-size="6"
            fill="#111111"
            fill-opacity="0.6"
            text-anchor="middle"
          >
            {{ tick.label }}
          </text>
        </svg>
        <svg
          :viewBox="`0 0 ${energyChart.width} ${energyChart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          :aria-label="t('inputShaping.fromPrinter.energyChartLabel')"
        >
          <polyline :points="energyChart.points" fill="none" stroke="#ff5247" stroke-width="1" />
          <circle
            v-if="energyChart.minMark"
            :cx="energyChart.minMark.x"
            :cy="energyChart.minMark.y"
            r="2"
            fill="#00e0c6"
            stroke="#111111"
            stroke-width="0.5"
          />
        </svg>
        <div class="flex flex-wrap gap-x-3 font-mono text-[10px] opacity-60">
          <span>{{ t('inputShaping.fromPrinter.specAxes') }}</span>
          <span>{{ t('inputShaping.fromPrinter.energyLegend') }}</span>
        </div>
      </div>
    </div>

    <!-- Vibrations profile: a long speed × motor-angle sweep → smoothest/worst speeds. -->
    <div class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[11px]">
        <span class="font-bold">{{ t('inputShaping.fromPrinter.vibTitle') }}</span>
        <label class="flex items-center gap-1"
          >{{ t('inputShaping.fromPrinter.vibMax') }}
          <input v-model="vibMaxSpeed" :class="numClass" />
          {{ t('inputShaping.fromPrinter.vibUnit') }}</label
        >
        <label class="flex items-center gap-1"
          >{{ t('inputShaping.fromPrinter.vibStep') }}
          <input v-model="vibIncrement" :class="numClass" />
          {{ t('inputShaping.fromPrinter.vibUnit') }}</label
        >
        <label class="flex items-center gap-1">
          <input v-model="vibReady" type="checkbox" />
          {{ t('inputShaping.fromPrinter.confirmMoves') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!vibReady || motionBusy"
          @click="runVib"
        >
          {{
            vibBusy
              ? t('inputShaping.fromPrinter.vibBtnBusy')
              : t('inputShaping.fromPrinter.vibBtn')
          }}
        </button>
      </div>
      <i18n-t
        keypath="inputShaping.fromPrinter.vibDesc"
        tag="p"
        scope="global"
        class="font-mono text-[10px] opacity-60"
      >
        <template #step
          ><strong>{{ t('inputShaping.fromPrinter.vibDescStep') }}</strong></template
        >
      </i18n-t>
      <HelpNote topic="vibrations" />
      <VibrationsProfile v-if="vibResult" :result="vibResult" />
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
  </div>
</template>
