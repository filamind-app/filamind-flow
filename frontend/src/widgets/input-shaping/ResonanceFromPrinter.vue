<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  analyzeResonanceFile,
  compareBelts,
  listResonanceFiles,
  measureNoise,
  runAxesMap,
  runLiveTest,
  runStaticExcitation,
} from './api'
import { buildAxesVelocityChart } from './axesChart'
import { angleClass, axesMapConfig, mappingArrow, matchVerdict, statusBg } from './axesMap'
import { beltVerdict, buildCompareChart } from './compare'
import { buildEnergyTimeline, buildSpectrogram } from './spectrogram-chart'
import type {
  AxesMapResult,
  BeltComparison,
  NoiseResult,
  ResonanceFile,
  ShaperAnalysis,
  StaticExcitationResult,
} from './types'

const emit = defineEmits<{ analyzed: [ShaperAnalysis] }>()

const files = ref<ResonanceFile[]>([])
const dirs = ref<string[]>([])
const error = ref<string | null>(null)
const busy = ref(false)
const liveAxis = ref<'x' | 'y'>('x')
const liveReady = ref(false)
const liveBusy = ref(false)
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
  () => liveBusy.value || beltsBusy.value || axesBusy.value || staticBusy.value,
)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'
const numClass = `${inputClass} w-14 font-mono`

function noiseClass(grade: NoiseResult['grade']): string {
  if (grade === 'good') return 'bg-brand-lime'
  if (grade === 'elevated') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
function noiseVerdict(grade: NoiseResult['grade']): string {
  if (grade === 'good') return '✅ quiet'
  if (grade === 'elevated') return '⚠ elevated'
  return '⛔ too noisy'
}

function msg(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

function kb(size: number): string {
  return size >= 1024 ? `${(size / 1024).toFixed(0)} KB` : `${size} B`
}

async function loadFiles(): Promise<void> {
  error.value = null
  try {
    const r = await listResonanceFiles()
    files.value = r.files
    dirs.value = r.dirs
  } catch (e) {
    error.value = msg(e, 'Could not list printer files')
  }
}

async function importFile(f: ResonanceFile): Promise<void> {
  if (busy.value) return
  error.value = null
  busy.value = true
  try {
    emit('analyzed', await analyzeResonanceFile(f.path, f.axis ?? undefined))
  } catch (e) {
    error.value = msg(e, 'Analysis failed')
  } finally {
    busy.value = false
  }
}

async function checkNoise(): Promise<void> {
  if (noiseBusy.value) return
  error.value = null
  noiseBusy.value = true
  try {
    noise.value = await measureNoise()
  } catch (e) {
    error.value = msg(e, 'Noise check failed')
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
    await loadFiles()
  } catch (e) {
    error.value = msg(e, 'Live test failed')
  } finally {
    liveBusy.value = false
  }
}

async function runBelts(): Promise<void> {
  if (beltsBusy.value || !liveReady.value) return
  error.value = null
  beltsBusy.value = true
  try {
    belts.value = await compareBelts()
    liveReady.value = false
    await loadFiles()
  } catch (e) {
    error.value = msg(e, 'Belt comparison failed')
  } finally {
    beltsBusy.value = false
  }
}

async function runAxes(): Promise<void> {
  if (axesBusy.value || !liveReady.value) return
  error.value = null
  axesBusy.value = true
  try {
    axesMapResult.value = await runAxesMap()
    liveReady.value = false
  } catch (e) {
    error.value = msg(e, 'Axes-map detection failed')
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
    error.value = 'Copy failed — select the text and copy it manually.'
  }
}

async function runStatic(): Promise<void> {
  if (staticBusy.value || !staticReady.value) return
  error.value = null
  staticBusy.value = true
  try {
    staticResult.value = await runStaticExcitation(
      staticAxis.value,
      Number(staticFreq.value) || 50,
      Number(staticDuration.value) || 15,
    )
    staticReady.value = false
  } catch (e) {
    error.value = msg(e, 'Sustain-frequency test failed')
  } finally {
    staticBusy.value = false
  }
}

onMounted(loadFiles)
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <div class="flex items-center justify-between">
      <span class="text-xs font-bold uppercase tracking-wide">From the printer</span>
      <button class="nb-btn px-2 py-0.5 text-[10px]" @click="loadFiles">↻ refresh</button>
    </div>

    <!-- Accelerometer noise pre-check — motion-free, validates the sensor mount. -->
    <div class="space-y-1 rounded-brutal border-2 border-dashed border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[10px]">
        <span class="font-bold">🔊 Noise check</span>
        <button class="nb-btn px-2 py-0.5" :disabled="noiseBusy" @click="checkNoise">
          {{ noiseBusy ? 'measuring…' : 'MEASURE_AXES_NOISE' }}
        </button>
        <span class="opacity-60">motion-free · run before testing</span>
      </div>
      <div v-if="noise" class="space-y-0.5">
        <div class="flex flex-wrap items-center gap-2">
          <span class="nb-badge" :class="noiseClass(noise.grade)">{{
            noiseVerdict(noise.grade)
          }}</span>
          <span class="font-mono text-[9px] opacity-60"
            >max {{ noise.max_noise.toFixed(1) }} · normal &lt; {{ noise.threshold }}</span
          >
        </div>
        <div v-for="c in noise.chips" :key="c.label" class="font-mono text-[9px] opacity-70">
          {{ c.label }}: x {{ c.x.toFixed(1) }} · y {{ c.y.toFixed(1) }} · z {{ c.z.toFixed(1) }}
        </div>
      </div>
    </div>

    <!-- Live test: moves the toolhead, so it is gated behind a confirm checkbox. -->
    <div class="space-y-1 rounded-brutal border-2 border-dashed border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[10px]">
        <span class="font-bold">🔴 Live test</span>
        <select v-model="liveAxis" :class="inputClass">
          <option value="x">axis X</option>
          <option value="y">axis Y</option>
        </select>
        <label class="flex items-center gap-1">
          <input v-model="liveReady" type="checkbox" /> ⚠ moves the toolhead — I'm ready
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || motionBusy"
          @click="live"
        >
          {{ liveBusy ? 'running…' : 'run TEST_RESONANCES' }}
        </button>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || motionBusy"
          title="CoreXY: excite each belt diagonal and overlay the responses"
          @click="runBelts"
        >
          {{ beltsBusy ? 'comparing…' : '🟰 compare belts' }}
        </button>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || motionBusy"
          title="Jog +X/+Y/+Z to detect the accelerometer orientation (axes_map)"
          @click="runAxes"
        >
          {{ axesBusy ? 'detecting…' : '🧭 axes map' }}
        </button>
      </div>
      <p class="font-mono text-[9px] opacity-60">
        Homes the printer if needed, then runs TEST_RESONANCES (needs an accelerometer + a
        <code>[resonance_tester]</code>). Refused while printing.
        <strong>Compare belts</strong> runs two sweeps along the CoreXY belt diagonals;
        <strong>axes map</strong> jogs ~30 mm in X, Y, Z to detect the sensor orientation.
      </p>
    </div>

    <!-- Belt comparison (CoreXY): the two belt-direction responses overlaid. -->
    <div
      v-if="belts && beltChart && beltJudge"
      class="space-y-1 rounded-brutal border-2 border-ink p-2"
    >
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[10px] font-bold uppercase tracking-wide">Belt comparison</span>
        <span
          class="nb-badge"
          :class="beltJudge.level === 'good' ? 'bg-brand-lime' : 'bg-brand-yellow'"
          >{{ beltJudge.matched ? '✅' : '⚠' }} {{ beltJudge.title }}</span
        >
        <span class="font-mono text-[9px] opacity-60"
          >A {{ beltJudge.peakA.toFixed(1) }} Hz vs B {{ beltJudge.peakB.toFixed(1) }} Hz · Δ{{
            beltJudge.diffPct.toFixed(0)
          }}%</span
        >
      </div>
      <svg
        :viewBox="`0 0 ${beltChart.width} ${beltChart.height}`"
        class="w-full rounded-brutal border-2 border-ink bg-paper"
        role="img"
        aria-label="Belt A vs B frequency response"
      >
        <line
          v-for="t in beltChart.xTicks"
          :key="'bg' + t.label"
          :x1="t.x"
          :x2="t.x"
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
          v-for="t in beltChart.xTicks"
          :key="'bt' + t.label"
          :x="t.x"
          :y="beltChart.height - 2"
          font-size="6"
          fill="#111111"
          fill-opacity="0.6"
          text-anchor="middle"
        >
          {{ t.label }}
        </text>
      </svg>
      <p class="text-[9px] opacity-70">{{ beltJudge.advice }}</p>
      <div class="flex gap-3 font-mono text-[9px]">
        <span class="flex items-center gap-1"
          ><span class="inline-block h-0 w-3 border-t-2" style="border-color: #5b8cff" /> belt A
          (1,1)</span
        >
        <span class="flex items-center gap-1"
          ><span
            class="inline-block h-0 w-3 border-t-2 border-dashed"
            style="border-color: #ff5247"
          />
          belt B (1,-1)</span
        >
      </div>
    </div>

    <!-- Axes-map detection: orientation + the paste-ready axes_map. -->
    <div v-if="axesMapResult && axesChart" class="space-y-1 rounded-brutal border-2 border-ink p-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[10px] font-bold uppercase tracking-wide">Axes map</span>
        <span class="nb-badge font-mono text-xs" :class="statusBg(axesMapResult.status)">{{
          axesMapResult.axes_map
        }}</span>
        <button class="nb-btn px-2 py-0.5 text-[10px]" @click="copyAxesMap">
          {{ axesCopied ? '✅ Copied' : '📋 Copy' }}
        </button>
      </div>
      <p class="text-[9px] opacity-70">{{ matchVerdict(axesMapResult) }}</p>
      <div class="flex flex-wrap gap-1.5 font-mono text-[9px]">
        <span
          v-for="m in axesMapResult.mappings"
          :key="m.machine_axis"
          class="nb-badge"
          :class="m.extrapolated ? 'bg-surface opacity-60' : angleClass(m.angle_error)"
        >
          {{ mappingArrow(m) }}{{ m.extrapolated ? ' (virtual)' : ` ${m.angle_error.toFixed(0)}°` }}
        </span>
      </div>
      <svg
        :viewBox="`0 0 ${axesChart.width} ${axesChart.height}`"
        class="w-full rounded-brutal border-2 border-ink bg-paper"
        role="img"
        aria-label="Axis velocity sequence"
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
            {{ z.extrapolated ? 'virtual' : (z.confidence * 100).toFixed(0) + '%' }}
          </text>
        </template>
      </svg>
      <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[9px] opacity-70">
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #ff5247" />accel x</span
        >
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #5b8cff" />y</span
        >
        <span class="flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded-sm" style="background: #00e0c6" />z</span
        >
        <span
          >tilt {{ axesMapResult.euler.x?.toFixed(1) }}° / {{ axesMapResult.euler.y?.toFixed(1) }}°
          / {{ axesMapResult.euler.z?.toFixed(1) }}°</span
        >
        <span>gravity {{ axesMapResult.gravity.toFixed(2) }} m/s²</span>
        <span :class="axesMapResult.noise_grade === 'ok' ? '' : 'text-brand-red'"
          >noise {{ axesMapResult.noise.toFixed(0) }}</span
        >
      </div>
      <p v-if="axesMapResult.messages.length" class="text-[9px] opacity-60">
        {{ axesMapResult.messages.join(' · ') }}
      </p>
    </div>

    <!-- Sustain frequency: hold a frequency in place to find what rattles by hand. -->
    <div class="space-y-1 rounded-brutal border-2 border-dashed border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[10px]">
        <span class="font-bold">🎯 Sustain frequency</span>
        <select v-model="staticAxis" :class="inputClass">
          <option value="x">X</option>
          <option value="y">Y</option>
        </select>
        <label class="flex items-center gap-1"
          >Hz <input v-model="staticFreq" :class="numClass"
        /></label>
        <label class="flex items-center gap-1"
          >sec <input v-model="staticDuration" :class="numClass"
        /></label>
        <label class="flex items-center gap-1">
          <input v-model="staticReady" type="checkbox" /> ⚠ moves the toolhead — I'm ready
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!staticReady || motionBusy"
          @click="runStatic"
        >
          {{ staticBusy ? 'holding…' : 'run' }}
        </button>
      </div>
      <p class="font-mono text-[9px] opacity-60">
        Buzzes the toolhead in place near the frequency — touch belts, the toolhead and frame to
        find what rattles. Refused while printing.
      </p>
      <div v-if="staticResult && specChart && energyChart" class="space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="nb-badge"
            :class="staticResult.dominant_ok ? 'bg-brand-lime' : 'bg-brand-yellow'"
            >{{ staticResult.dominant_ok ? '✅ holding' : '⚠ off-target' }}</span
          >
          <span class="font-mono text-[9px] opacity-60"
            >peak {{ staticResult.dominant_freq.toFixed(0) }} Hz ·
            {{ staticResult.excited_band_pct.toFixed(0) }}% in band</span
          >
        </div>
        <p class="text-[9px] opacity-80">{{ staticResult.verdict }}</p>
        <svg
          :viewBox="`0 0 ${specChart.width} ${specChart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          aria-label="Frequency-time spectrogram"
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
            v-for="t in specChart.freqTicks"
            :key="'ft' + t.label"
            :x="t.x"
            :y="specChart.height - 2"
            font-size="6"
            fill="#111111"
            fill-opacity="0.6"
            text-anchor="middle"
          >
            {{ t.label }}
          </text>
        </svg>
        <svg
          :viewBox="`0 0 ${energyChart.width} ${energyChart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          aria-label="Vibration energy over time"
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
        <div class="flex flex-wrap gap-x-3 font-mono text-[9px] opacity-60">
          <span>freq → · time ↓</span>
          <span>energy vs time — the cyan dip is where a touch helped</span>
        </div>
      </div>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <!-- Resonance CSVs already on the host. -->
    <p v-if="!files.length" class="font-mono text-[10px] opacity-60">
      No resonance CSVs found{{ dirs.length ? ` in ${dirs.join(', ')}` : '' }}.
    </p>
    <div v-for="f in files" :key="f.path" class="flex items-center gap-2 font-mono text-[10px]">
      <span v-if="f.axis" class="nb-badge shrink-0 bg-brand-cyan">{{ f.axis.toUpperCase() }}</span>
      <span class="min-w-0 flex-1 truncate">{{ f.name }}</span>
      <span class="shrink-0 opacity-50">{{ kb(f.size) }}</span>
      <button class="nb-btn shrink-0 px-2 py-0.5" :disabled="busy" @click="importFile(f)">
        analyze
      </button>
    </div>
  </div>
</template>
