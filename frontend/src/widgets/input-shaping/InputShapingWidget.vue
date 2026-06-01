<script setup lang="ts">
import { computed, ref } from 'vue'

import { analyzeResonance } from './api'
import { inputShaperConfig } from './config'
import type { ShaperAnalysis } from './types'

const file = ref<File | null>(null)
const axis = ref<'auto' | 'x' | 'y'>('auto')
const analysis = ref<ShaperAnalysis | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const copied = ref(false)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

const configText = computed(() => (analysis.value ? inputShaperConfig([analysis.value]) : ''))

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
    analysis.value = await analyzeResonance(file.value, {
      axis: axis.value === 'auto' ? undefined : axis.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Analysis failed'
  } finally {
    busy.value = false
  }
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
      <code>TEST_RESONANCES</code>, then upload the resulting <code>.csv</code>.
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
      <span v-if="file" class="min-w-0 truncate font-mono text-[10px] opacity-60">{{
        file.name
      }}</span>
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

      <div class="space-y-1">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold uppercase tracking-wide">printer.cfg</span>
          <button class="nb-btn px-2 py-0.5 text-[10px]" @click="copyConfig">
            {{ copied ? '✅ Copied' : '📋 Copy' }}
          </button>
        </div>
        <pre
          class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
          >{{ configText }}</pre
        >
        <p class="text-[9px] italic opacity-50">
          Paste into your <code>printer.cfg</code>, then restart Klipper.
        </p>
      </div>
    </template>
  </div>
</template>
