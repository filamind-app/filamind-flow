<script setup lang="ts">
/** Renders a machine vibrations profile: the speed-energy curve (with smoothest bands
 *  + resonance peaks marked), a polar energy plot by travel direction, an angle×speed
 *  heatmap, and the motor health stats. Pure presentation over a VibrationsProfile.
 */
import { computed } from 'vue'

import type { VibrationsProfile } from './types'
import { buildPolarAngles, buildSpeedProfile, buildVibHeatmap } from './vibrations'

const props = defineProps<{ result: VibrationsProfile }>()

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
      <span class="text-[10px] font-bold uppercase tracking-wide">Vibrations profile</span>
      <span v-if="result.low_freq_warning" class="nb-badge bg-brand-red text-surface"
        >⚠ low-freq noise</span
      >
      <span v-else-if="result.recommended_speed != null" class="nb-badge bg-brand-cyan"
        >▼ smoothest ~{{ result.recommended_speed.toFixed(0) }} mm/s</span
      >
      <span class="nb-badge" :class="symmetryClass(result.symmetry_pct)"
        >symmetry {{ result.symmetry_pct.toFixed(0) }}%</span
      >
      <span class="font-mono text-[9px] opacity-60"
        >{{ result.kinematics }} · {{ result.accel }} mm/s²</span
      >
    </div>

    <p class="text-[9px] opacity-80">{{ result.verdict }}</p>

    <!-- Speed-energy profile: the main curve + smoothest bands + peaks to avoid. -->
    <svg
      :viewBox="`0 0 ${speedChart.width} ${speedChart.height}`"
      class="w-full rounded-brutal border-2 border-ink bg-paper"
      role="img"
      aria-label="Vibration energy versus speed"
    >
      <rect
        v-for="(b, i) in speedChart.bands"
        :key="'band' + i"
        :x="b.x"
        :y="8"
        :width="b.w"
        :height="speedChart.height - 22"
        fill="#9be15d"
        fill-opacity="0.3"
      />
      <line
        v-for="(p, i) in speedChart.peaks"
        :key="'peak' + i"
        :x1="p.x"
        :x2="p.x"
        :y1="8"
        :y2="speedChart.height - 14"
        stroke="#ff5247"
        stroke-width="0.8"
        stroke-dasharray="2 1.5"
      />
      <line
        v-if="speedChart.recommendedX != null"
        :x1="speedChart.recommendedX"
        :x2="speedChart.recommendedX"
        :y1="8"
        :y2="speedChart.height - 14"
        stroke="#00b3a0"
        stroke-width="1"
      />
      <polyline
        v-if="speedChart.maxPoints"
        :points="speedChart.maxPoints"
        fill="none"
        stroke="#111111"
        stroke-opacity="0.25"
        stroke-width="0.8"
        stroke-dasharray="2 2"
      />
      <polyline :points="speedChart.energyPoints" fill="none" stroke="#ff5247" stroke-width="1.2" />
      <text
        v-for="t in speedChart.speedTicks"
        :key="'st' + t.label"
        :x="t.x"
        :y="speedChart.height - 3"
        font-size="6"
        fill="#111111"
        fill-opacity="0.6"
        text-anchor="middle"
      >
        {{ t.label }}
      </text>
    </svg>
    <div class="flex flex-wrap gap-x-3 font-mono text-[9px] opacity-60">
      <span>speed (mm/s) → · vibration energy ↑</span>
      <span class="flex items-center gap-1"
        ><span class="inline-block h-2 w-3 rounded-sm" style="background: #9be15d" />smooth</span
      >
      <span class="flex items-center gap-1"
        ><span
          class="inline-block h-0 w-3 border-t-2 border-dashed"
          style="border-color: #ff5247"
        />
        avoid</span
      >
    </div>

    <div class="flex flex-wrap gap-2">
      <!-- Polar energy by travel direction. -->
      <svg
        :viewBox="`0 0 ${polar.size} ${polar.size}`"
        class="rounded-brutal border-2 border-ink bg-paper"
        style="width: 150px; height: 150px"
        role="img"
        aria-label="Vibration energy by travel direction"
      >
        <circle
          :cx="polar.cx"
          :cy="polar.cy"
          :r="polar.gridR"
          fill="none"
          stroke="#111111"
          stroke-opacity="0.2"
          stroke-width="0.5"
        />
        <circle
          :cx="polar.cx"
          :cy="polar.cy"
          :r="polar.gridR / 2"
          fill="none"
          stroke="#111111"
          stroke-opacity="0.12"
          stroke-width="0.5"
        />
        <polygon
          :points="polar.polygon"
          fill="#00e0c6"
          fill-opacity="0.35"
          stroke="#00b3a0"
          stroke-width="1"
        />
        <line
          v-for="(s, i) in polar.spokes"
          :key="'spoke' + i"
          :x1="polar.cx"
          :y1="polar.cy"
          :x2="s.x"
          :y2="s.y"
          stroke="#111111"
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
          fill="#111111"
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
        aria-label="Vibration energy heatmap by angle and speed"
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
          v-for="t in heatmap.speedTicks"
          :key="'hst' + t.label"
          :x="t.x"
          :y="heatmap.height - 3"
          font-size="6"
          fill="#111111"
          fill-opacity="0.6"
          text-anchor="middle"
        >
          {{ t.label }}
        </text>
        <text
          v-for="t in heatmap.angleTicks"
          :key="'hat' + t.label"
          :x="3"
          :y="t.y + 2"
          font-size="5.5"
          fill="#111111"
          fill-opacity="0.55"
        >
          {{ t.label }}
        </text>
      </svg>
    </div>

    <!-- Smoothest / worst speeds + good directions + motor resonance. -->
    <div class="flex flex-wrap gap-1 font-mono text-[9px]">
      <span
        v-for="(r, i) in result.good_speed_ranges.slice(0, 3)"
        :key="'gs' + i"
        class="nb-badge bg-brand-lime"
        >✓ {{ r.start.toFixed(0) }}–{{ r.end.toFixed(0) }} mm/s</span
      >
      <span
        v-for="(p, i) in result.peak_speeds.slice(0, 5)"
        :key="'ps' + i"
        class="nb-badge bg-brand-red text-surface"
        >✕ {{ p.toFixed(0) }}</span
      >
    </div>
    <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[9px] opacity-70">
      <span v-if="result.motor_freq != null"
        >motor resonance {{ result.motor_freq.toFixed(0) }} Hz<span
          v-if="result.motor_damping != null"
        >
          · ζ {{ result.motor_damping.toFixed(3) }}</span
        ></span
      >
      <span v-if="result.good_angle_ranges.length"
        >smoothest direction ~{{ result.good_angle_ranges[0].start.toFixed(0) }}–{{
          result.good_angle_ranges[0].end.toFixed(0)
        }}°</span
      >
      <span>{{ result.segments_used }} captures</span>
    </div>
  </div>
</template>
