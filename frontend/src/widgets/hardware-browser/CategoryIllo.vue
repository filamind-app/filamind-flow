<script setup lang="ts">
/** A small hand-drawn glyph representing each hardware category (for the catalog tiles).
 *  Neo-Brutalist line-art (thick currentColor strokes). Falls back to a generic box. */
import { computed } from 'vue'

const props = defineProps<{ category: string }>()

const key = computed(() => {
  const c = props.category.toLowerCase()
  if (c.includes('stepper motor')) return 'motor'
  if (c.includes('driver')) return 'driver'
  if (c.includes('mcu') || c.includes('board')) return 'board'
  if (c.includes('host')) return 'host'
  if (c.includes('sensor') || c.includes('probe')) return 'sensor'
  if (c.includes('electronic') || c.includes('wiring')) return 'wiring'
  if (c.includes('nozzle')) return 'nozzle'
  if (c.includes('motion') || c.includes('mechanical')) return 'motion'
  if (c.includes('hotend') || c.includes('heater')) return 'hotend'
  if (c.includes('camera') || c.includes('display')) return 'camera'
  if (c.includes('fan') || c.includes('power') || c.includes('bed')) return 'fan'
  if (c.includes('extruder')) return 'extruder'
  if (c.includes('filament')) return 'filament'
  return 'generic'
})
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- motor: body + shaft -->
    <g v-if="key === 'motor'">
      <rect x="5" y="6" width="11" height="12" rx="1" />
      <line x1="16" y1="12" x2="20" y2="12" />
      <line x1="7" y1="6" x2="7" y2="18" />
    </g>
    <!-- driver chip -->
    <g v-else-if="key === 'driver'">
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <path d="M4 9h3M4 12h3M4 15h3M17 9h3M17 12h3M17 15h3" />
    </g>
    <!-- board -->
    <g v-else-if="key === 'board'">
      <rect x="3" y="5" width="18" height="14" rx="1" />
      <rect x="6" y="8" width="5" height="5" />
      <path d="M14 9h4M14 12h4M14 15h4" />
    </g>
    <!-- host (SBC) -->
    <g v-else-if="key === 'host'">
      <rect x="4" y="6" width="16" height="11" rx="1" />
      <path d="M9 20h6M12 17v3" />
    </g>
    <!-- sensor / probe -->
    <g v-else-if="key === 'sensor'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    </g>
    <!-- wiring / connector -->
    <g v-else-if="key === 'wiring'">
      <path d="M4 9c4 0 4 6 8 6s4-6 8-6" />
      <rect x="3" y="6" width="3" height="6" rx="1" />
      <rect x="18" y="12" width="3" height="6" rx="1" />
    </g>
    <!-- nozzle -->
    <g v-else-if="key === 'nozzle'">
      <path d="M8 5h8l-1 6H9z" />
      <path d="M9 11l2 6h2l2-6" />
      <line x1="11.5" y1="20" x2="12.5" y2="20" />
    </g>
    <!-- motion / gear -->
    <g v-else-if="key === 'motion'">
      <circle cx="12" cy="12" r="4" />
      <path
        d="M12 4v2M12 18v2M4 12h2M18 12h2M6 6l1.5 1.5M16.5 16.5L18 18M18 6l-1.5 1.5M7.5 16.5L6 18"
      />
    </g>
    <!-- hotend (heatsink fins + block) -->
    <g v-else-if="key === 'hotend'">
      <path d="M8 4h8M8 7h8M8 10h8" />
      <rect x="8" y="12" width="8" height="5" rx="1" />
      <path d="M10 17l2 3 2-3" />
    </g>
    <!-- camera -->
    <g v-else-if="key === 'camera'">
      <rect x="3" y="7" width="18" height="12" rx="2" />
      <circle cx="12" cy="13" r="3" />
      <path d="M8 7l1.5-2h5L16 7" />
    </g>
    <!-- fan -->
    <g v-else-if="key === 'fan'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 12c0-4 4-5 4-2s-4 2-4 2 4 1 4 4-4 1-4-2 -4 1-4-2 4-2 4-2-4-1-4-4 4-1 4 2" />
    </g>
    <!-- extruder (gear + filament) -->
    <g v-else-if="key === 'extruder'">
      <circle cx="10" cy="12" r="5" />
      <circle cx="10" cy="12" r="1.5" />
      <path d="M15 12h6M18 9v6" />
    </g>
    <!-- filament spool -->
    <g v-else-if="key === 'filament'">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M20 12h2" />
    </g>
    <!-- generic -->
    <g v-else>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 12h8" />
    </g>
  </svg>
</template>
