<script setup lang="ts">
/** Frequency-response chart for one shaper analysis: PSD curves (front) over the
 *  shaper-reduction curves (behind), with the dominant resonance peak marked. Extracted
 *  from the widget so the Guided wizard can render one chart per stage (X, then Y, ...)
 *  without the latest analysis replacing the previous one. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { buildResponseChart } from './chart'
import type { ShaperAnalysis } from './types'

const props = defineProps<{ analysis: ShaperAnalysis }>()
const { t } = useI18n({ useScope: 'global' })

const chart = computed(() => buildResponseChart(props.analysis))

/** Keeps the peak label inside the plot - flips to the left of the marker near the right edge. */
function peakLabelX(x: number, width: number): number {
  return x > width * 0.78 ? x - 3 : x + 3
}
</script>

<template>
  <div v-if="chart && chart.psd.length" class="space-y-1">
    <svg
      :viewBox="`0 0 ${chart.width} ${chart.height}`"
      class="w-full rounded-brutal border-2 border-ink bg-paper"
      role="img"
      :aria-label="t('inputShaping.widget.chartAria')"
    >
      <line
        v-for="tick in chart.xTicks"
        :key="'g' + tick.label"
        :x1="tick.x"
        :x2="tick.x"
        :y1="6"
        :y2="chart.height - 12"
        class="stroke-ink"
        stroke-opacity="0.12"
        stroke-width="0.5"
      />
      <!-- Noise floor (median PSD) - anything near it is just noise. -->
      <line
        v-if="chart.noiseY != null"
        :x1="4"
        :x2="chart.width - 4"
        :y1="chart.noiseY"
        :y2="chart.noiseY"
        class="stroke-ink"
        stroke-opacity="0.3"
        stroke-width="0.5"
        stroke-dasharray="3 2"
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
      <!-- Dominant resonance peak. -->
      <g v-if="chart.peak">
        <line
          :x1="chart.peak.x"
          :x2="chart.peak.x"
          :y1="6"
          :y2="chart.height - 12"
          class="stroke-brand-red"
          stroke-width="0.6"
          stroke-dasharray="2 1.5"
        />
        <circle
          :cx="chart.peak.x"
          :cy="chart.peak.y"
          r="2.2"
          class="fill-brand-red stroke-ink"
          stroke-width="0.5"
        />
        <text
          :x="peakLabelX(chart.peak.x, chart.width)"
          :y="11"
          font-size="6.5"
          font-weight="bold"
          class="fill-brand-red"
          :text-anchor="chart.peak.x > chart.width * 0.78 ? 'end' : 'start'"
        >
          {{ t('inputShaping.widget.peakLabel', { v: chart.peak.label }) }}
        </text>
      </g>
      <text
        v-for="tick in chart.xTicks"
        :key="'t' + tick.label"
        :x="tick.x"
        :y="chart.height - 2"
        font-size="6"
        class="fill-ink"
        fill-opacity="0.6"
        text-anchor="middle"
      >
        {{ tick.label }}
      </text>
    </svg>
    <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px]">
      <span v-for="s in chart.psd" :key="'lg' + s.name" class="flex items-center gap-1">
        <span class="inline-block h-2 w-3 rounded-sm" :style="{ background: s.color }" />
        {{ s.name }}
      </span>
      <span class="flex items-center gap-1 opacity-70">
        <span class="inline-block h-0 w-3 border-t-2 border-brand-pink" />
        {{ t('inputShaping.widget.legendRecommended') }}
      </span>
      <span class="flex items-center gap-1 text-brand-red">{{
        t('inputShaping.widget.legendPeak')
      }}</span>
      <span class="opacity-50">{{ t('inputShaping.widget.legendAxisHint') }}</span>
    </div>
  </div>
</template>
