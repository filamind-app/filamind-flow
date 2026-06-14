<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchDriverStatus, fetchMotorCatalog, saveMotorAssignment } from './api'
import { pendingStepper } from './driverFocus'
import HelpIllo from './HelpIllo.vue'
import GuidedWizard from './GuidedWizard.vue'
import HomingPanel from './HomingPanel.vue'
import LiveMonitor from './LiveMonitor.vue'
import MotorPicker from './MotorPicker.vue'
import MotorSyncPanel from './MotorSyncPanel.vue'
import RecommendPanel from './RecommendPanel.vue'
import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import RegisterEditor from './RegisterEditor.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
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
import type { DriversStatus, MotorSpec, TmcDriver } from './types'

const { t } = useI18n({ useScope: 'global' })

const status = ref<DriversStatus | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)
const motorCatalog = ref<MotorSpec[]>([])
const mode = ref<'dashboard' | 'guided'>('dashboard')
const MODE_TABS = computed<{ id: 'dashboard' | 'guided'; label: string }[]>(() => [
  { id: 'dashboard', label: t('motorDrivers.widget.tabDashboard') },
  { id: 'guided', label: t('motorDrivers.widget.tabGuided') },
])
/** Per-card "details" disclosure — keeps the secondary specs off the baseline card (#119). */
const openDetails = ref<Record<string, boolean>>({})

const drivers = computed(() => status.value?.drivers ?? [])

// Inbound cross-widget focus: jump to one stepper's card (from the Machine Map, a doctor
// finding, …) and flash it so the eye lands on the right driver.
const highlightStepper = ref<string | null>(null)
function applyDriverFocus(): void {
  const stepper = pendingStepper.value
  if (!stepper || !drivers.value.some((d) => d.stepper === stepper)) return
  pendingStepper.value = null
  highlightStepper.value = stepper
  void nextTick(() => {
    document
      .getElementById(`drv-${stepper}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  window.setTimeout(() => {
    if (highlightStepper.value === stepper) highlightStepper.value = null
  }, 2500)
}
watch(pendingStepper, applyDriverFocus)
watch(drivers, applyDriverFocus)
const reachable = computed(() => status.value?.reachable ?? false)

function healthTitle(d: TmcDriver): string {
  return driverHealth(d).tone === 'idle'
    ? t('motorDrivers.widget.healthTitleIdle')
    : t('motorDrivers.widget.healthTitleLive')
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
        {{ t('motorDrivers.widget.intro') }}
      </p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="motorDrivers"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="motorDrivers.widget.steps"
          :button-label="t('motorDrivers.help.guide')"
          :title="t('motorDrivers.help.guideTitle')"
          :close-label="t('motorDrivers.help.close')"
          :steps-title="t('motorDrivers.help.howToRead')"
        />
        <HelpIllo illo="driver" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- Dashboard / Guided mode strip — shown once the printer is reachable, so the Guided
         wizard is discoverable even before any driver is assigned a motor (#119). -->
    <WidgetTabs v-if="reachable" v-model="mode" :tabs="MODE_TABS" />

    <!-- States -->
    <div v-if="loading && !status" class="font-mono text-xs">
      {{ t('motorDrivers.widget.loading') }}
    </div>

    <!-- A failed poll with NO prior data is a real empty/error state; with data on screen it
         becomes a stale-data banner — one bad 6s poll must not blank a live dashboard. -->
    <div
      v-else-if="error && !status"
      class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red px-2 py-1 text-surface"
    >
      <span role="alert" class="min-w-0 flex-1 text-[11px]">{{ error }}</span>
      <div class="flex shrink-0 items-center gap-2">
        <button
          class="nb-btn bg-surface px-2 py-0.5 text-[11px] text-ink"
          :disabled="loading"
          @click="load()"
        >
          {{ loading ? t('motorDrivers.widget.retrying') : t('motorDrivers.widget.retry') }}
        </button>
        <ReportErrorButton :error="error" />
      </div>
    </div>

    <!-- Stale-data banner: the dashboard stays, the failed refresh is disclosed. -->
    <div
      v-if="error && status"
      class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-yellow/30 px-2 py-1"
    >
      <span class="min-w-0 flex-1 text-[11px]">{{ t('motorDrivers.widget.staleData') }}</span>
      <button
        class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[11px]"
        :disabled="loading"
        @click="load()"
      >
        {{ loading ? t('motorDrivers.widget.retrying') : t('motorDrivers.widget.retry') }}
      </button>
    </div>

    <p
      v-else-if="!reachable"
      class="rounded-brutal border-2 border-ink bg-brand-yellow px-2 py-1 text-[11px]"
    >
      {{ t('motorDrivers.widget.unreachable') }}
    </p>

    <p v-else-if="!drivers.length" class="font-mono text-xs opacity-70">
      {{ t('motorDrivers.widget.noDrivers') }}
    </p>

    <!-- Driver cards (dashboard mode) -->
    <template v-else-if="mode === 'dashboard'">
      <div class="grid gap-2 sm:grid-cols-2">
        <section
          v-for="d in drivers"
          :id="`drv-${d.stepper}`"
          :key="d.stepper"
          class="space-y-1.5 rounded-brutal border-2 border-ink bg-surface p-2"
          :class="{ 'ring-4 ring-brand-cyan': highlightStepper === d.stepper }"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ axisHeading(d) }}</div>
              <div class="font-mono text-[11px] opacity-60">{{ d.stepper }}</div>
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
              <i18n-t keypath="motorDrivers.widget.runCurrent" tag="span" scope="global">
                <template #value
                  ><b>{{ currentLabel(d.run_current, d.run_current_config) }}</b></template
                >
              </i18n-t>
              <span
                v-if="nearCurrentCap(d)"
                class="text-brand-red"
                :title="t('motorDrivers.widget.nearCapTitle', { max: maxCurrentLabel(d) })"
                >⚠</span
              >
            </span>
            <span class="opacity-80">{{
              t('motorDrivers.widget.holdCurrent', {
                value: currentLabel(d.hold_current, d.hold_current_config),
              })
            }}</span>
          </div>

          <!-- Essentials stay inline; the rest collapses behind a per-card "details" toggle. -->
          <div
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[11px] opacity-80"
          >
            <span>{{ chopperLabel(d) }}</span>
            <span v-if="d.microsteps != null">{{
              t('motorDrivers.widget.microsteps', { n: d.microsteps })
            }}</span>
            <span>{{ temperatureLabel(d) }}</span>
            <span v-if="d.stallguard_field">{{
              t('motorDrivers.widget.sg', {
                field: d.stallguard_field,
                threshold: d.stallguard_threshold,
              })
            }}</span>
            <button
              class="opacity-60 transition-opacity hover:opacity-100"
              :aria-expanded="!!openDetails[d.stepper]"
              @click="openDetails[d.stepper] = !openDetails[d.stepper]"
            >
              {{
                openDetails[d.stepper]
                  ? t('motorDrivers.widget.detailsHide')
                  : t('motorDrivers.widget.detailsShow')
              }}
            </button>
          </div>

          <div
            v-if="openDetails[d.stepper]"
            class="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] opacity-70"
          >
            <span v-if="d.interpolate">{{ t('motorDrivers.widget.interp') }}</span>
            <span v-if="d.sense_resistor != null">{{
              t('motorDrivers.widget.sense', { value: d.sense_resistor })
            }}</span>
            <span v-if="interfaceLabel(d)">{{ interfaceLabel(d) }}</span>
            <span v-if="maxCurrentLabel(d)">{{ maxCurrentLabel(d) }}</span>
            <span
              v-for="c in capabilityChips(effectiveCapabilities(d))"
              :key="c"
              class="nb-badge bg-paper px-1.5 py-0 text-[10px]"
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
