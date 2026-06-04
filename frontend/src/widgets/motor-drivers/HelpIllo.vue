<script setup lang="ts">
/** Neutral teaching illustrations for the Motor Drivers help notes — one per HelpIlloKey.
 *  Dependency-free 24×24 line art (currentColor), ≤6 strokes each, theme-aware.
 */
import type { HelpIlloKey } from './help'

defineProps<{ illo: HelpIlloKey }>()
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    role="img"
    aria-hidden="true"
  >
    <!-- Driver chip wired to a stepper motor -->
    <g v-if="illo === 'driver'">
      <rect x="3" y="8" width="8" height="8" rx="1" />
      <circle cx="18" cy="12" r="4" />
      <line x1="11" y1="12" x2="14" y2="12" />
      <line x1="18" y1="9.5" x2="18" y2="14.5" />
    </g>

    <!-- Coil current waveform -->
    <g v-else-if="illo === 'current'">
      <line x1="3" y1="12" x2="21" y2="12" stroke-opacity="0.4" />
      <path d="M3 12 C 5 5, 7 5, 9 12 S 13 19, 15 12 S 19 5, 21 12" />
    </g>

    <!-- StealthChop (smooth, top) vs SpreadCycle (chopped, bottom) -->
    <g v-else-if="illo === 'chopper'">
      <path d="M3 8 q 2 -3 4 0 t 4 0 t 4 0 t 4 0" />
      <path d="M3 18 h2 v-4 h2 v4 h2 v-4 h2 v4 h2 v-4 h2 v4" />
    </g>

    <!-- Microstepping staircase -->
    <g v-else-if="illo === 'microsteps'">
      <path d="M3 20 h3 v-3 h3 v-3 h3 v-3 h3 v-3 h3" />
    </g>

    <!-- Homing: a microswitch endstop with its lever + roller -->
    <g v-else-if="illo === 'homing'">
      <rect x="3" y="10" width="9" height="6" rx="1" />
      <line x1="12" y1="11" x2="20" y2="6" />
      <circle cx="20.5" cy="5.5" r="1.5" />
      <line x1="6" y1="16" x2="6" y2="20" />
      <line x1="9" y1="16" x2="9" y2="20" />
    </g>

    <!-- StallGuard: motor pushing against a wall (sensorless stop) -->
    <g v-else>
      <circle cx="8" cy="12" r="5" />
      <line x1="20" y1="5" x2="20" y2="19" />
      <line x1="14" y1="12" x2="18" y2="12" />
      <path d="M16.5 10 l2 2 l-2 2" />
    </g>
  </svg>
</template>
