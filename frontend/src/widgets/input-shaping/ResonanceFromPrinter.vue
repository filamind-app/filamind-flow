<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  analyzeResonanceFile,
  compareBelts,
  listResonanceFiles,
  measureNoise,
  runLiveTest,
} from './api'
import { beltVerdict, buildCompareChart } from './compare'
import type { BeltComparison, NoiseResult, ResonanceFile, ShaperAnalysis } from './types'

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

const beltChart = computed(() =>
  belts.value ? buildCompareChart(belts.value.belt_a, belts.value.belt_b) : null,
)
const beltJudge = computed(() =>
  belts.value ? beltVerdict(belts.value.belt_a, belts.value.belt_b) : null,
)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

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
          :disabled="!liveReady || liveBusy || beltsBusy"
          @click="live"
        >
          {{ liveBusy ? 'running…' : 'run TEST_RESONANCES' }}
        </button>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || liveBusy || beltsBusy"
          title="CoreXY: excite each belt diagonal and overlay the responses"
          @click="runBelts"
        >
          {{ beltsBusy ? 'comparing…' : '🟰 compare belts' }}
        </button>
      </div>
      <p class="font-mono text-[9px] opacity-60">
        Homes the printer if needed, then runs TEST_RESONANCES (needs an accelerometer + a
        <code>[resonance_tester]</code>). Refused while printing.
        <strong>Compare belts</strong> runs two sweeps along the CoreXY belt diagonals.
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
