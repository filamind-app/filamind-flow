<script setup lang="ts">
/** The Machine Doctor's headline glyph: a segmented ring (one arc per setup step, filled when the
 *  step is done) with the letter grade in the middle. A fresh, untuned printer shows a mostly-empty
 *  ring, so incompleteness - not the grade - is what the eye lands on first. On-theme
 *  (Neo-Brutalist): ink-bordered grade chip, brand-lime for done, faint ink for still-to-do. */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    done: number
    total: number
    grade: string
    gradeClass: string
    size?: number
  }>(),
  { size: 96 },
)

const stroke = computed(() => Math.max(6, Math.round(props.size * 0.1)))
const radius = computed(() => (props.size - stroke.value) / 2 - 1)
const center = computed(() => props.size / 2)
const chip = computed(() => Math.round(props.size * 0.52))

const GAP_DEG = 8 // gap between segments so they read as discrete steps

function polar(deg: number): [number, number] {
  const a = ((deg - 90) * Math.PI) / 180
  return [center.value + radius.value * Math.cos(a), center.value + radius.value * Math.sin(a)]
}

function arcPath(a0: number, a1: number): string {
  const [x0, y0] = polar(a0)
  const [x1, y1] = polar(a1)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${x0} ${y0} A ${radius.value} ${radius.value} 0 ${large} 1 ${x1} ${y1}`
}

const segments = computed(() => {
  const n = Math.max(props.total, 1)
  const span = 360 / n
  return Array.from({ length: n }, (_, i) => ({
    d: arcPath(i * span + GAP_DEG / 2, (i + 1) * span - GAP_DEG / 2),
    done: i < props.done,
  }))
})
</script>

<template>
  <div
    class="relative inline-flex shrink-0 items-center justify-center"
    :style="{ width: size + 'px', height: size + 'px' }"
    role="img"
    :aria-label="`${done}/${total}`"
  >
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <path
        v-for="(s, i) in segments"
        :key="i"
        :d="s.d"
        fill="none"
        stroke="currentColor"
        :stroke-width="stroke"
        stroke-linecap="round"
        :class="s.done ? 'text-brand-lime' : 'text-ink/15'"
      />
    </svg>
    <span
      class="absolute flex items-center justify-center rounded-brutal border-2 border-ink font-display font-bold text-ink"
      :class="gradeClass"
      :style="{ width: chip + 'px', height: chip + 'px', fontSize: Math.round(size * 0.28) + 'px' }"
    >
      {{ grade }}
    </span>
  </div>
</template>
