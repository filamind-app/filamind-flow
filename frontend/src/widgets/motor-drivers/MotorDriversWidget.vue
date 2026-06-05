<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchDriverStatus, fetchMotorCatalog, saveMotorAssignment } from './api'
import HelpIllo from './HelpIllo.vue'
import GuidedWizard from './GuidedWizard.vue'
import HelpNote from './HelpNote.vue'
import HomingPanel from './HomingPanel.vue'
import LiveMonitor from './LiveMonitor.vue'
import MotorPicker from './MotorPicker.vue'
import MotorSyncPanel from './MotorSyncPanel.vue'
import RecommendPanel from './RecommendPanel.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import { describeError } from '@/core/describeError'

import RegisterEditor from './RegisterEditor.vue'
import {
  axisHeading,
  capabilityChips,
  chopperLabel,
  currentLabel,
  driverHealth,
  driverModelLabel,
  effectiveCapabilities,
  healthClass,
  homingApplies,
  interfaceLabel,
  maxCurrentLabel,
  nearCurrentCap,
  temperatureLabel,
} from './format'
import { STEPS } from './help'
import type { DriversStatus, MotorSpec, TmcDriver } from './types'

const status = ref<DriversStatus | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)
const showSteps = ref(false)
const motorCatalog = ref<MotorSpec[]>([])
const mode = ref<'dashboard' | 'guided'>('dashboard')
const MODE_TABS: { id: 'dashboard' | 'guided'; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'guided', label: '🧭 Guided' },
]
/** Per-card "details" disclosure — keeps the secondary specs off the baseline card (#119). */
const openDetails = ref<Record<string, boolean>>({})

const drivers = computed(() => status.value?.drivers ?? [])
const reachable = computed(() => status.value?.reachable ?? false)

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

/** Persist a motor assignment, then refresh so the card shows the motor's specs. */
async function onAssign(stepper: string, model: string | null): Promise<void> {
  try {
    await saveMotorAssignment(stepper, model)
    await load(true)
  } catch (e) {
    error.value = describeError(e)
  }
}

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  void load()
  // The motor catalog is static reference data — fetch once (best-effort).
  fetchMotorCatalog()
    .then((c) => (motorCatalog.value = c.motors))
    .catch(() => {})
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
        Every TMC stepper driver on your printer, read live from its Klipper config — inspect, get
        tuning recommendations, and apply them (gated). New here? Try 🧭 Guided.
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

    <!-- Dashboard / Guided mode strip — shown once the printer is reachable, so the Guided
         wizard is discoverable even before any driver is assigned a motor (#119). -->
    <WidgetTabs v-if="reachable" v-model="mode" :tabs="MODE_TABS" />

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

    <!-- Driver cards (dashboard mode) -->
    <template v-else-if="mode === 'dashboard'">
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

          <!-- Essentials stay inline; the rest collapses behind a per-card "details" toggle. -->
          <div
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[10px] opacity-80"
          >
            <span>{{ chopperLabel(d) }}</span>
            <span v-if="d.microsteps != null">{{ d.microsteps }} µsteps</span>
            <span>{{ temperatureLabel(d) }}</span>
            <span v-if="d.stallguard_field"
              >SG {{ d.stallguard_field }} {{ d.stallguard_threshold }}</span
            >
            <button
              class="opacity-60 transition-opacity hover:opacity-100"
              :aria-expanded="!!openDetails[d.stepper]"
              @click="openDetails[d.stepper] = !openDetails[d.stepper]"
            >
              {{ openDetails[d.stepper] ? '▾ less' : '▸ details' }}
            </button>
          </div>

          <div
            v-if="openDetails[d.stepper]"
            class="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] opacity-70"
          >
            <span v-if="d.interpolate">interp</span>
            <span v-if="d.sense_resistor != null">sense {{ d.sense_resistor }} Ω</span>
            <span v-if="interfaceLabel(d)">{{ interfaceLabel(d) }}</span>
            <span v-if="maxCurrentLabel(d)">{{ maxCurrentLabel(d) }}</span>
            <span
              v-for="c in capabilityChips(effectiveCapabilities(d))"
              :key="c"
              class="nb-badge bg-paper px-1.5 py-0 text-[9px]"
              >{{ c }}</span
            >
          </div>

          <LiveMonitor :driver="d" />

          <MotorPicker
            :stepper="d.stepper"
            :assigned="d.motor"
            :catalog="motorCatalog"
            @assign="onAssign"
          />

          <RecommendPanel v-if="d.motor" :driver="d" @applied="load(true)" />

          <HomingPanel v-if="homingApplies(d.homing_method)" :driver="d" @changed="load(true)" />

          <RegisterEditor :driver="d" @changed="load(true)" />
        </section>
      </div>

      <!-- Printer-level: motor synchronization (dual/quad-motor axes) -->
      <MotorSyncPanel />

      <!-- Contextual help (all collapsed) -->
      <div class="flex flex-wrap gap-x-3 gap-y-1 pt-1">
        <HelpNote topic="current" />
        <HelpNote topic="chopper" />
        <HelpNote topic="microsteps" />
        <HelpNote topic="stallguard" />
        <HelpNote topic="health" />
        <HelpNote topic="catalog" />
        <HelpNote topic="motor" />
        <HelpNote topic="recommend" />
        <HelpNote topic="homing" />
        <HelpNote topic="sensorless" />
        <HelpNote topic="monitor" />
        <HelpNote topic="motorsync" />
        <HelpNote topic="registers" />
      </div>
    </template>

    <!-- Guided wizard mode -->
    <GuidedWizard
      v-else
      :drivers="drivers"
      :catalog="motorCatalog"
      @changed="load(true)"
      @exit="mode = 'dashboard'"
    />
  </div>
</template>
