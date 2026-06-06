<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { analyzeResonance } from './api'
import { buildCompareChart, compareAnalyses, type CompareRow } from './compare'
import type { ShaperAnalysis } from './types'

const { t } = useI18n({ useScope: 'global' })

const fileA = ref<File | null>(null)
const fileB = ref<File | null>(null)
const resA = ref<ShaperAnalysis | null>(null)
const resB = ref<ShaperAnalysis | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

const rows = computed(() =>
  resA.value && resB.value ? compareAnalyses(resA.value, resB.value) : [],
)
const plot = computed(() =>
  resA.value && resB.value ? buildCompareChart(resA.value, resB.value) : null,
)

function pick(target: 'a' | 'b', event: Event): void {
  const f = (event.target as HTMLInputElement).files?.[0] ?? null
  if (target === 'a') fileA.value = f
  else fileB.value = f
}

async function run(): Promise<void> {
  if (!fileA.value || !fileB.value || busy.value) return
  error.value = null
  busy.value = true
  try {
    const [a, b] = await Promise.all([analyzeResonance(fileA.value), analyzeResonance(fileB.value)])
    resA.value = a
    resB.value = b
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('inputShaping.compareView.comparisonFailed')
  } finally {
    busy.value = false
  }
}

const TREND_CLASS: Record<CompareRow['trend'], string> = {
  better: 'bg-brand-lime/60 font-bold',
  worse: 'bg-brand-red/20',
  same: 'opacity-50',
  neutral: '',
}
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <span class="text-xs font-bold uppercase tracking-wide">{{
      t('inputShaping.compareView.title')
    }}</span>
    <p class="font-mono text-[11px] opacity-60">
      {{ t('inputShaping.compareView.intro') }}
    </p>

    <div class="flex flex-wrap items-center gap-2 text-[11px]">
      <label class="nb-btn cursor-pointer px-2 py-0.5">
        {{ t('inputShaping.compareView.selectA') }}
        <input type="file" accept=".csv" class="hidden" @change="(e) => pick('a', e)" />
      </label>
      <span v-if="fileA" class="max-w-[7rem] truncate font-mono opacity-60">{{ fileA.name }}</span>
      <span class="font-bold">⇄</span>
      <label class="nb-btn cursor-pointer px-2 py-0.5">
        {{ t('inputShaping.compareView.selectB') }}
        <input type="file" accept=".csv" class="hidden" @change="(e) => pick('b', e)" />
      </label>
      <span v-if="fileB" class="max-w-[7rem] truncate font-mono opacity-60">{{ fileB.name }}</span>
      <button
        class="nb-btn bg-brand-lime px-2 py-0.5"
        :disabled="!fileA || !fileB || busy"
        @click="run"
      >
        {{ busy ? t('inputShaping.compareView.busy') : t('inputShaping.compareView.compare') }}
      </button>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <template v-if="plot && rows.length">
      <svg
        :viewBox="`0 0 ${plot.width} ${plot.height}`"
        class="w-full rounded-brutal border-2 border-ink bg-surface"
        role="img"
        :aria-label="t('inputShaping.compareView.chartAriaLabel')"
      >
        <line
          v-for="tick in plot.xTicks"
          :key="'g' + tick.label"
          :x1="tick.x"
          :x2="tick.x"
          :y1="6"
          :y2="plot.height - 12"
          stroke="#111111"
          stroke-opacity="0.12"
          stroke-width="0.5"
        />
        <polyline :points="plot.a.points" fill="none" :stroke="plot.a.color" stroke-width="1" />
        <polyline
          :points="plot.b.points"
          fill="none"
          :stroke="plot.b.color"
          stroke-width="1"
          stroke-dasharray="2 2"
        />
        <text
          v-for="tick in plot.xTicks"
          :key="'t' + tick.label"
          :x="tick.x"
          :y="plot.height - 2"
          font-size="6"
          fill="#111111"
          fill-opacity="0.6"
          text-anchor="middle"
        >
          {{ tick.label }}
        </text>
      </svg>

      <div class="space-y-0.5">
        <div
          class="grid grid-cols-[1fr_auto_auto] gap-3 border-b-2 border-ink pb-0.5 font-mono text-[11px] font-bold uppercase"
        >
          <span></span>
          <span class="text-end text-brand-blue">{{ t('inputShaping.compareView.colA') }}</span>
          <span class="text-end text-brand-red">{{ t('inputShaping.compareView.colB') }}</span>
        </div>
        <div
          v-for="row in rows"
          :key="row.label"
          class="grid grid-cols-[1fr_auto_auto] items-center gap-3 font-mono text-[11px]"
        >
          <span class="opacity-70">{{ row.label }}</span>
          <span class="text-end">{{ row.a }}</span>
          <span class="rounded px-1 text-end" :class="TREND_CLASS[row.trend]">{{ row.b }}</span>
        </div>
      </div>
    </template>
  </div>
</template>
