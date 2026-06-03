<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchDriverStatus } from './api'
import HelpIllo from './HelpIllo.vue'
import HelpNote from './HelpNote.vue'
import {
  axisHeading,
  capabilityChips,
  chopperLabel,
  currentLabel,
  driverHealth,
  driverModelLabel,
  effectiveCapabilities,
  healthClass,
  interfaceLabel,
  maxCurrentLabel,
  nearCurrentCap,
  temperatureLabel,
} from './format'
import { STEPS } from './help'
import type { DriversStatus, TmcDriver } from './types'

const status = ref<DriversStatus | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)
const showSteps = ref(false)
const openRegisters = ref<Record<string, boolean>>({})

const drivers = computed(() => status.value?.drivers ?? [])
const reachable = computed(() => status.value?.reachable ?? false)

/** Maps a raw fetch failure to a clear, actionable message (same resilience as the
 *  other widgets — never blank, never a bare "Failed to fetch"). */
function describeError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|fetch/i.test(m)) {
    return 'Cannot reach the FilaMind backend — check that the filamind-flow service is running and reachable.'
  }
  return m
}

/** Raw driver_* registers as printable [name, value] pairs for the advanced view. */
function registerEntries(d: TmcDriver): [string, string][] {
  return Object.entries(d.registers).map(([k, v]) => [k, String(v)])
}

function toggleRegisters(stepper: string): void {
  openRegisters.value[stepper] = !openRegisters.value[stepper]
}

function healthTitle(d: TmcDriver): string {
  return driverHealth(d).tone === 'idle'
    ? 'Enable the motor (home or jog an axis) to read live temperature and fault flags'
    : 'Live driver status from drv_status'
}

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    status.value = await fetchDriverStatus()
    error.value = null
  } catch (e) {
    // Surface failures on silent refreshes too, so a poll that fails never blanks the panel.
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  void load()
  timer = setInterval(() => void load(true), 6000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help layer (collapsed by default — zero clutter) -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">
        Every TMC stepper driver on your printer, read live from its Klipper config. Read-only —
        tuning comes later.
      </p>
      <HelpIllo illo="driver" class="h-8 w-8 shrink-0 opacity-70" />
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <HelpNote topic="overview" />
      <HelpNote topic="glossary" />
      <button
        class="font-mono text-[10px] opacity-60 transition-opacity hover:opacity-100"
        :aria-expanded="showSteps"
        @click="showSteps = !showSteps"
      >
        {{ showSteps ? '▾ how to read this' : '▸ how to read this' }}
      </button>
    </div>
    <ol
      v-if="showSteps"
      class="list-decimal space-y-1 rounded-brutal border-2 border-dashed border-ink bg-paper py-2 pl-6 pr-2 text-[11px] leading-snug opacity-80"
    >
      <li v-for="(s, i) in STEPS" :key="i">{{ s }}</li>
    </ol>

    <!-- States -->
    <div v-if="loading && !status" class="font-mono text-xs">Loading motor drivers…</div>

    <div
      v-else-if="error"
      class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red px-2 py-1 text-surface"
    >
      <span class="min-w-0 flex-1 text-[11px]">{{ error }}</span>
      <button
        class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[10px] text-ink"
        :disabled="loading"
        @click="load()"
      >
        {{ loading ? 'retrying…' : '↻ retry' }}
      </button>
    </div>

    <p
      v-else-if="!reachable"
      class="rounded-brutal border-2 border-ink bg-brand-yellow px-2 py-1 text-[11px]"
    >
      Can’t reach the printer’s Moonraker — driver data is unavailable right now.
    </p>

    <p v-else-if="!drivers.length" class="font-mono text-xs opacity-70">
      No TMC drivers found in the Klipper config. (Only TMC stepper drivers appear here.)
    </p>

    <!-- Driver cards -->
    <template v-else>
      <div class="grid gap-2 sm:grid-cols-2">
        <section
          v-for="d in drivers"
          :key="d.stepper"
          class="space-y-1.5 rounded-brutal border-2 border-ink bg-surface p-2"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ axisHeading(d) }}</div>
              <div class="font-mono text-[10px] opacity-60">{{ d.stepper }}</div>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <span class="nb-badge bg-brand-cyan">{{ driverModelLabel(d.model) }}</span>
              <span
                class="nb-badge"
                :class="healthClass(driverHealth(d).tone)"
                :title="healthTitle(d)"
                >{{ driverHealth(d).label }}</span
              >
            </div>
          </div>

          <div class="flex items-center justify-between font-mono text-[11px]">
            <span>
              Run <b>{{ currentLabel(d.run_current, d.run_current_config) }}</b>
              <span
                v-if="nearCurrentCap(d)"
                class="text-brand-red"
                :title="`Near this model's rated cap (${maxCurrentLabel(d)})`"
                >⚠</span
              >
            </span>
            <span class="opacity-80"
              >Hold {{ currentLabel(d.hold_current, d.hold_current_config) }}</span
            >
          </div>

          <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] opacity-80">
            <span>{{ chopperLabel(d) }}</span>
            <span v-if="d.microsteps != null">{{ d.microsteps }} µsteps</span>
            <span v-if="d.interpolate">interp</span>
            <span v-if="d.sense_resistor != null">sense {{ d.sense_resistor }} Ω</span>
            <span>{{ temperatureLabel(d) }}</span>
            <span v-if="d.stallguard_field"
              >SG {{ d.stallguard_field }} {{ d.stallguard_threshold }}</span
            >
            <span v-if="interfaceLabel(d)" class="opacity-70">{{ interfaceLabel(d) }}</span>
            <span v-if="maxCurrentLabel(d)" class="opacity-70">{{ maxCurrentLabel(d) }}</span>
          </div>

          <div v-if="capabilityChips(effectiveCapabilities(d)).length" class="flex flex-wrap gap-1">
            <span
              v-for="c in capabilityChips(effectiveCapabilities(d))"
              :key="c"
              class="nb-badge bg-paper px-1.5 py-0 text-[9px]"
              >{{ c }}</span
            >
          </div>

          <div v-if="registerEntries(d).length" class="font-mono text-[10px]">
            <button
              class="opacity-60 transition-opacity hover:opacity-100"
              :aria-expanded="!!openRegisters[d.stepper]"
              @click="toggleRegisters(d.stepper)"
            >
              {{ openRegisters[d.stepper] ? '▾' : '▸' }} advanced registers
            </button>
            <dl
              v-if="openRegisters[d.stepper]"
              class="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
            >
              <div v-for="[k, v] in registerEntries(d)" :key="k" class="flex justify-between gap-1">
                <dt class="opacity-60">{{ k }}</dt>
                <dd class="font-bold">{{ v }}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <!-- Contextual help (all collapsed) -->
      <div class="flex flex-wrap gap-x-3 gap-y-1 pt-1">
        <HelpNote topic="current" />
        <HelpNote topic="chopper" />
        <HelpNote topic="microsteps" />
        <HelpNote topic="stallguard" />
        <HelpNote topic="health" />
        <HelpNote topic="catalog" />
      </div>
    </template>
  </div>
</template>
