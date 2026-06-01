<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import ResonanceCompare from './ResonanceCompare.vue'
import { analyzeResonance } from './api'
import { buildResponseChart } from './chart'
import { inputShaperConfig } from './config'
import type { ShaperAnalysis } from './types'

const file = ref<File | null>(null)
const axis = ref<'auto' | 'x' | 'y'>('auto')
const analysis = ref<ShaperAnalysis | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const copied = ref(false)
const showAdvanced = ref(false)
const showCompare = ref(false)

/** Advanced calibration knobs (kept as strings for the inputs; blank = default). */
const params = reactive({ maxFreq: '200', scv: '5', maxSmoothing: '', dampingRatio: '' })

/** Results accumulated per axis ('x' / 'y') or 'generic' (no axis), so an X and a
 *  Y capture combine into a single config block. */
const byAxis = reactive<Record<string, ShaperAnalysis>>({})

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'
const numClass = `${inputClass} w-16 font-mono`

const captured = computed(() => ['generic', 'x', 'y'].filter((k) => byAxis[k]))
const configText = computed(() => {
  const list = ['x', 'y', 'generic'].map((k) => byAxis[k]).filter(Boolean) as ShaperAnalysis[]
  return list.length ? inputShaperConfig(list) : ''
})
const chart = computed(() => (analysis.value ? buildResponseChart(analysis.value) : null))

function num(value: string, fallback: number): number {
  const n = Number(value)
  return value.trim() !== '' && Number.isFinite(n) ? n : fallback
}

function onPick(event: Event): void {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  analysis.value = null
  error.value = null
}

async function analyze(): Promise<void> {
  if (!file.value || busy.value) return
  error.value = null
  busy.value = true
  try {
    const ax = axis.value === 'auto' ? undefined : axis.value
    const result = await analyzeResonance(file.value, {
      axis: ax,
      maxFreq: num(params.maxFreq, 200),
      scv: num(params.scv, 5),
      maxSmoothing: params.maxSmoothing.trim() ? Number(params.maxSmoothing) : undefined,
      dampingRatio: params.dampingRatio.trim() ? Number(params.dampingRatio) : undefined,
    })
    analysis.value = result
    // A generic capture replaces any per-axis ones and vice versa, so the config
    // block never mixes `shaper_type` with `shaper_type_x`.
    const key = ax ?? 'generic'
    if (key === 'generic') {
      delete byAxis.x
      delete byAxis.y
    } else {
      delete byAxis.generic
    }
    byAxis[key] = result
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Analysis failed'
  } finally {
    busy.value = false
  }
}

function clearResults(): void {
  analysis.value = null
  for (const key of Object.keys(byAxis)) delete byAxis[key]
}

async function copyConfig(): Promise<void> {
  if (!configText.value) return
  try {
    await navigator.clipboard.writeText(configText.value)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1500)
  } catch {
    error.value = 'Copy failed — select the text and copy it manually.'
  }
}
</script>

<template>
  <div class="space-y-3 text-sm">
    <p class="font-mono text-[11px] opacity-70">
      Find the best input shaper from a Klipper resonance CSV — no command line. Capture data with
      <code>TEST_RESONANCES</code>, then upload the resulting <code>.csv</code>. Analyze the X and Y
      files in turn to build one config block.
    </p>

    <div class="flex flex-wrap items-center gap-2">
      <label class="nb-btn cursor-pointer px-2 py-1 text-xs">
        📈 Select CSV
        <input type="file" accept=".csv" class="hidden" @change="onPick" />
      </label>
      <select v-model="axis" :class="inputClass" title="Axis this data belongs to">
        <option value="auto">axis: auto</option>
        <option value="x">axis: X</option>
        <option value="y">axis: Y</option>
      </select>
      <button
        class="nb-btn bg-brand-lime px-3 py-1 text-xs"
        :disabled="!file || busy"
        @click="analyze"
      >
        {{ busy ? 'Analyzing…' : '🚀 Analyze' }}
      </button>
      <button class="nb-btn px-2 py-1 text-[10px]" @click="showAdvanced = !showAdvanced">
        ⚙ advanced
      </button>
      <button class="nb-btn px-2 py-1 text-[10px]" @click="showCompare = !showCompare">
        ⇄ compare
      </button>
      <span v-if="file" class="min-w-0 truncate font-mono text-[10px] opacity-60">{{
        file.name
      }}</span>
    </div>

    <div
      v-if="showAdvanced"
      class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-brutal border-2 border-dashed border-ink bg-paper px-2 py-1.5 font-mono text-[10px]"
    >
      <label class="flex items-center gap-1"
        >max_freq <input v-model="params.maxFreq" :class="numClass"
      /></label>
      <label class="flex items-center gap-1"
        >scv <input v-model="params.scv" :class="numClass"
      /></label>
      <label class="flex items-center gap-1"
        >max_smoothing <input v-model="params.maxSmoothing" placeholder="—" :class="numClass"
      /></label>
      <label class="flex items-center gap-1"
        >damping_ratio <input v-model="params.dampingRatio" placeholder="—" :class="numClass"
      /></label>
      <span class="opacity-50">blank = Klipper default</span>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <template v-if="analysis">
      <div
        v-if="analysis.recommended_shaper"
        class="flex flex-wrap items-center gap-2 rounded-brutal border-2 border-ink bg-brand-lime px-3 py-2"
      >
        <span class="text-xs font-bold uppercase tracking-wide">Recommended</span>
        <span class="font-mono text-base font-bold">{{
          analysis.recommended_shaper.toUpperCase()
        }}</span>
        <span class="font-mono text-sm">@ {{ analysis.recommended_freq?.toFixed(1) }} Hz</span>
        <span v-if="analysis.axis" class="nb-badge bg-surface">
          axis {{ analysis.axis.toUpperCase() }}
        </span>
      </div>
      <div v-else class="nb-badge bg-brand-yellow">No shaper recommended for this data.</div>

      <!-- Frequency response: PSD curves (front) over shaper-reduction curves (behind). -->
      <div v-if="chart && chart.psd.length" class="space-y-1">
        <svg
          :viewBox="`0 0 ${chart.width} ${chart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          aria-label="Frequency response and shapers"
        >
          <line
            v-for="t in chart.xTicks"
            :key="'g' + t.label"
            :x1="t.x"
            :x2="t.x"
            :y1="6"
            :y2="chart.height - 12"
            stroke="#111111"
            stroke-opacity="0.12"
            stroke-width="0.5"
          />
          <polyline
            v-for="s in chart.shapers"
            :key="'sh' + s.name"
            :points="s.points"
            fill="none"
            :stroke="s.color"
            stroke-width="0.8"
            :stroke-dasharray="s.dashed ? '2 2' : ''"
          />
          <polyline
            v-for="s in chart.psd"
            :key="'psd' + s.name"
            :points="s.points"
            fill="none"
            :stroke="s.color"
            stroke-width="1"
          />
          <text
            v-for="t in chart.xTicks"
            :key="'t' + t.label"
            :x="t.x"
            :y="chart.height - 2"
            font-size="6"
            fill="#111111"
            fill-opacity="0.6"
            text-anchor="middle"
          >
            {{ t.label }}
          </text>
        </svg>
        <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[9px]">
          <span v-for="s in chart.psd" :key="'lg' + s.name" class="flex items-center gap-1">
            <span class="inline-block h-2 w-3 rounded-sm" :style="{ background: s.color }" />
            {{ s.name }}
          </span>
          <span class="flex items-center gap-1 opacity-70">
            <span class="inline-block h-0 w-3 border-t-2" style="border-color: #ff5c8a" />
            recommended
          </span>
          <span class="opacity-50">Hz · left PSD · right vibration reduction</span>
        </div>
      </div>

      <div class="space-y-1">
        <div
          class="grid grid-cols-[1fr_auto_auto_auto_auto] gap-3 border-b-2 border-ink pb-0.5 font-mono text-[10px] font-bold uppercase"
        >
          <span>shaper</span>
          <span class="text-right">freq</span>
          <span class="text-right">vibr</span>
          <span class="text-right">smooth</span>
          <span class="text-right">accel</span>
        </div>
        <div
          v-for="s in analysis.shapers"
          :key="s.name"
          class="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 rounded px-1 font-mono text-[10px]"
          :class="s.recommended ? 'bg-brand-lime/50 font-bold' : ''"
        >
          <span>{{ s.name.toUpperCase() }}</span>
          <span class="text-right">{{ s.freq.toFixed(1) }} Hz</span>
          <span class="text-right">{{ s.vibrations_pct.toFixed(1) }}%</span>
          <span class="text-right">{{ s.smoothing.toFixed(3) }}</span>
          <span class="text-right">≤{{ s.max_accel.toFixed(0) }}</span>
        </div>
      </div>
    </template>

    <!-- Combined config block (accumulates across the X and Y captures). -->
    <div v-if="configText" class="space-y-1">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-bold uppercase tracking-wide">printer.cfg</span>
        <span class="flex items-center gap-1 font-mono text-[9px] opacity-70">
          <span v-for="k in captured" :key="k" class="nb-badge bg-brand-cyan">{{
            k === 'generic' ? 'X+Y' : k.toUpperCase()
          }}</span>
        </span>
        <span class="flex-1"></span>
        <button class="nb-btn px-2 py-0.5 text-[10px]" @click="copyConfig">
          {{ copied ? '✅ Copied' : '📋 Copy' }}
        </button>
        <button class="nb-btn px-2 py-0.5 text-[10px]" @click="clearResults">clear</button>
      </div>
      <pre
        class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
        >{{ configText }}</pre
      >
      <p class="text-[9px] italic opacity-50">
        Paste into your <code>printer.cfg</code>, then restart Klipper.
      </p>
    </div>

    <ResonanceCompare v-if="showCompare" />
  </div>
</template>
