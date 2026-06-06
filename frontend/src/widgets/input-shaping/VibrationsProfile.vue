<script setup lang="ts">
/** Renders a machine vibrations profile: the speed-energy curve (with smoothest bands
 *  + resonance peaks marked), a polar energy plot by travel direction, an angle×speed
 *  heatmap, and the motor health stats. Pure presentation over a VibrationsProfile.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { VibrationsProfile } from './types'
import { buildPolarAngles, buildSpeedProfile, buildVibHeatmap } from './vibrations'

const props = defineProps<{ result: VibrationsProfile }>()

const { t } = useI18n({ useScope: 'global' })

const speedChart = computed(() => buildSpeedProfile(props.result))
const polar = computed(() => buildPolarAngles(props.result))
const heatmap = computed(() => buildVibHeatmap(props.result))

function symmetryClass(pct: number): string {
  if (pct >= 70) return 'bg-brand-lime'
  if (pct >= 40) return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
</script>

<template>
  <div class="space-y-1.5 rounded-brutal border-2 border-ink p-2">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-[11px] font-bold uppercase tracking-wide">{{
        t('inputShaping.vibrationsView.title')
      }}</span>
      <span v-if="result.low_freq_warning" class="nb-badge bg-brand-red text-surface">{{
        t('inputShaping.vibrationsView.lowFreqNoise')
      }}</span>
      <span v-else-if="result.recommended_speed != null" class="nb-badge bg-brand-cyan">{{
        t('inputShaping.vibrationsView.smoothest', { v: result.recommended_speed.toFixed(0) })
      }}</span>
      <span class="nb-badge" :class="symmetryClass(result.symmetry_pct)">{{
        t('inputShaping.vibrationsView.symmetry', { v: result.symmetry_pct.toFixed(0) })
      }}</span>
      <span class="font-mono text-[10px] opacity-60">{{
        t('inputShaping.vibrationsView.kinematicsAccel', {
          kin: result.kinematics,
          accel: result.accel,
        })
      }}</span>
    </div>

    <p class="text-[10px] opacity-80">{{ result.verdict }}</p>
    <!-- result.verdict is built by the vibrations helper (already translated). -->

    <!-- Speed-energy profile: the main curve + smoothest bands + peaks to avoid. -->
    <svg
      :viewBox="`0 0 ${speedChart.width} ${speedChart.height}`"
      class="w-full rounded-brutal border-2 border-ink bg-paper"
      role="img"
      :aria-label="t('inputShaping.vibrationsView.svgSpeedLabel')"
    >
      <rect
        v-for="(b, i) in speedChart.bands"
        :key="'band' + i"
        :x="b.x"
        :y="8"
        :width="b.w"
        :height="speedChart.height - 22"
        class="fill-brand-lime"
        fill-opacity="0.3"
      />
      <line
        v-for="(p, i) in speedChart.peaks"
        :key="'peak' + i"
        :x1="p.x"
        :x2="p.x"
        :y1="8"
        :y2="speedChart.height - 14"
        class="stroke-brand-red"
        stroke-width="0.8"
        stroke-dasharray="2 1.5"
      />
      <line
        v-if="speedChart.recommendedX != null"
        :x1="speedChart.recommendedX"
        :x2="speedChart.recommendedX"
        :y1="8"
        :y2="speedChart.height - 14"
        class="stroke-brand-cyan"
        stroke-width="1"
      />
      <polyline
        v-if="speedChart.maxPoints"
        :points="speedChart.maxPoints"
        fill="none"
        class="stroke-ink"
        stroke-opacity="0.25"
        stroke-width="0.8"
        stroke-dasharray="2 2"
      />
      <polyline
        :points="speedChart.energyPoints"
        fill="none"
        class="stroke-brand-red"
        stroke-width="1.2"
      />
      <text
        v-for="tick in speedChart.speedTicks"
        :key="'st' + tick.label"
        :x="tick.x"
        :y="speedChart.height - 3"
        font-size="6"
        class="fill-ink"
        fill-opacity="0.6"
        text-anchor="middle"
      >
        {{ tick.label }}
      </text>
    </svg>
    <div class="flex flex-wrap gap-x-3 font-mono text-[10px] opacity-60">
      <span>{{ t('inputShaping.vibrationsView.axisLegend') }}</span>
      <span class="flex items-center gap-1"
        ><span class="inline-block h-2 w-3 rounded-sm bg-brand-lime" />{{
          t('inputShaping.vibrationsView.smooth')
        }}</span
      >
      <span class="flex items-center gap-1"
        ><span class="inline-block h-0 w-3 border-t-2 border-brand-red" />
        {{ t('inputShaping.vibrationsView.avoid') }}</span
      >
    </div>

    <div class="flex flex-wrap gap-2">
      <!-- Polar energy by travel direction. -->
      <svg
        :viewBox="`0 0 ${polar.size} ${polar.size}`"
        class="rounded-brutal border-2 border-ink bg-paper"
        style="width: 150px; height: 150px"
        role="img"
        :aria-label="t('inputShaping.vibrationsView.svgPolarLabel')"
      >
        <circle
          :cx="polar.cx"
          :cy="polar.cy"
          :r="polar.gridR"
          fill="none"
          class="stroke-ink"
          stroke-opacity="0.2"
          stroke-width="0.5"
        />
        <circle
          :cx="polar.cx"
          :cy="polar.cy"
          :r="polar.gridR / 2"
          fill="none"
          class="stroke-ink"
          stroke-opacity="0.12"
          stroke-width="0.5"
        />
        <polygon
          :points="polar.polygon"
          class="fill-brand-cyan stroke-brand-cyan"
          fill-opacity="0.35"
          stroke-width="1"
        />
        <line
          v-for="(s, i) in polar.spokes"
          :key="'spoke' + i"
          :x1="polar.cx"
          :y1="polar.cy"
          :x2="s.x"
          :y2="s.y"
          class="stroke-ink"
          stroke-opacity="0.4"
          stroke-width="0.6"
          stroke-dasharray="2 2"
        />
        <text
          v-for="(s, i) in polar.spokes"
          :key="'spokel' + i"
          :x="s.x"
          :y="s.y"
          font-size="6"
          font-weight="bold"
          class="fill-ink"
          text-anchor="middle"
        >
          {{ s.label }}
        </text>
      </svg>

      <!-- Angle × speed heatmap. -->
      <svg
        :viewBox="`0 0 ${heatmap.width} ${heatmap.height}`"
        class="min-w-0 flex-1 rounded-brutal border-2 border-ink bg-paper"
        role="img"
        :aria-label="t('inputShaping.vibrationsView.svgHeatmapLabel')"
      >
        <rect
          v-for="(c, i) in heatmap.cells"
          :key="'h' + i"
          :x="c.x"
          :y="c.y"
          :width="c.w"
          :height="c.h"
          :fill="c.fill"
        />
        <text
          v-for="tick in heatmap.speedTicks"
          :key="'hst' + tick.label"
          :x="tick.x"
          :y="heatmap.height - 3"
          font-size="6"
          class="fill-ink"
          fill-opacity="0.6"
          text-anchor="middle"
        >
          {{ tick.label }}
        </text>
        <text
          v-for="tick in heatmap.angleTicks"
          :key="'hat' + tick.label"
          :x="3"
          :y="tick.y + 2"
          font-size="5.5"
          class="fill-ink"
          fill-opacity="0.55"
        >
          {{ tick.label }}
        </text>
      </svg>
    </div>

    <!-- Smoothest / worst speeds + good directions + motor resonance. -->
    <div class="flex flex-wrap gap-1 font-mono text-[10px]">
      <span
        v-for="(r, i) in result.good_speed_ranges.slice(0, 3)"
        :key="'gs' + i"
        class="nb-badge bg-brand-lime"
        >{{
          t('inputShaping.vibrationsView.goodSpeedRange', {
            start: r.start.toFixed(0),
            end: r.end.toFixed(0),
          })
        }}</span
      >
      <span
        v-for="(p, i) in result.peak_speeds.slice(0, 5)"
        :key="'ps' + i"
        class="nb-badge bg-brand-red text-surface"
        >{{ t('inputShaping.vibrationsView.peakSpeed', { v: p.toFixed(0) }) }}</span
      >
    </div>
    <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] opacity-70">
      <span v-if="result.motor_freq != null"
        >{{ t('inputShaping.vibrationsView.motorResonance', { v: result.motor_freq.toFixed(0) })
        }}<span v-if="result.motor_damping != null">
          {{
            t('inputShaping.vibrationsView.motorDamping', { v: result.motor_damping.toFixed(3) })
          }}</span
        ></span
      >
      <span v-if="result.good_angle_ranges.length">{{
        t('inputShaping.vibrationsView.smoothestDirection', {
          start: result.good_angle_ranges[0].start.toFixed(0),
          end: result.good_angle_ranges[0].end.toFixed(0),
        })
      }}</span>
      <span>{{ t('inputShaping.vibrationsView.captures', { n: result.segments_used }) }}</span>
    </div>
  </div>
</template>
