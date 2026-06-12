<script setup lang="ts">
/** Mission Control — the home page that answers "is my printer healthy?".
 *
 *  One `/api/overview` call renders: the live print state, the per-MCU firmware-sync table
 *  (computed by the backend since forever, rendered here for the first time), the latest tuning
 *  result per axis from the shaper archive, and whether the hardware changed against the saved
 *  Machine Map baseline. Every tile deep-links into the widget that owns the subject, and a
 *  Machine Doctor tile offers the full graded scan. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { resolveEndpoints } from '@/core/moonraker'
import { useNav } from '@/core/nav'
import { focusTopologyNode } from '@/widgets/board-topology/topologyFocus'

const { t } = useI18n({ useScope: 'global' })
const { go } = useNav()

interface OverviewMcu {
  name: string
  version: string | null
  in_sync: boolean | null
}
interface Overview {
  printer: {
    reachable: boolean
    state?: string
    filename?: string | null
    progress?: number | null
  }
  firmware: {
    available: boolean
    host_version?: string | null
    mcus: OverviewMcu[]
    out_of_sync?: number
  }
  tuning: {
    available: boolean
    axes: {
      axis: string
      shaper: string | null
      freq: number | null
      grade: string | null
      created: string | null
    }[]
  }
  hardware: { available: boolean; has_baseline: boolean; changes: number }
  setup?: { boards_identified: number; boards_total: number; motors_assigned: number }
}

const data = ref<Overview | null>(null)
const loading = ref(true)

async function load(): Promise<void> {
  loading.value = true
  try {
    const { backendUrl } = resolveEndpoints()
    const response = await fetch(`${backendUrl}/api/overview`)
    if (!response.ok) throw new Error(String(response.status))
    data.value = (await response.json()) as Overview
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}
onMounted(() => void load())

function stateBadge(state: string | undefined): { text: string; cls: string } {
  const s = state ?? 'unknown'
  if (s === 'printing')
    return { text: t('shell.home.statePrinting'), cls: 'bg-brand-red text-paper' }
  if (s === 'paused') return { text: t('shell.home.statePaused'), cls: 'bg-brand-yellow text-ink' }
  if (s === 'error') return { text: t('shell.home.stateError'), cls: 'bg-brand-red text-paper' }
  return { text: t('shell.home.stateIdle'), cls: 'bg-brand-lime text-ink' }
}

/** The Get-Started checklist: every step is detected from server data and jumps to its widget. */
interface SetupStep {
  key: string
  done: boolean
  go: () => void
}
const setupSteps = computed<SetupStep[]>(() => {
  const d = data.value
  if (!d) return []
  const setup = d.setup ?? { boards_identified: 0, boards_total: 0, motors_assigned: 0 }
  return [
    {
      key: 'boards',
      done: setup.boards_total > 0 && setup.boards_identified === setup.boards_total,
      go: () => go('board-topology'),
    },
    {
      key: 'baseline',
      done: d.hardware.has_baseline,
      go: () => go('board-topology'),
    },
    {
      key: 'firmware',
      done:
        d.firmware.available && !!d.firmware.host_version && (d.firmware.out_of_sync ?? 0) === 0,
      go: () => go('firmware-upgrade', 'status'),
    },
    {
      key: 'motors',
      done: setup.motors_assigned > 0,
      go: () => go('motor-drivers'),
    },
    {
      key: 'tuning',
      done: d.tuning.available && d.tuning.axes.length >= 2,
      go: () => go('input-shaping', 'guided'),
    },
  ]
})
const setupDone = computed(() => setupSteps.value.filter((s) => s.done).length)

function openMcu(name: string): void {
  focusTopologyNode(name)
  go('board-topology')
}
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-3">
    <div class="flex items-center justify-between gap-2">
      <h2 class="font-display text-2xl font-bold">{{ t('shell.home.title') }}</h2>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" :disabled="loading" @click="load">
        <span aria-hidden="true">↻</span> {{ t('shell.home.refresh') }}
      </button>
    </div>

    <p v-if="loading && !data" class="font-mono text-xs opacity-70">
      {{ t('shell.home.loading') }}
    </p>
    <p v-else-if="!data" class="nb-card bg-brand-red/10 p-3 font-mono text-xs">
      {{ t('shell.home.unreachable') }}
    </p>

    <!-- Get started: the existing wizards, sequenced into one journey (auto-detected) -->
    <details
      v-if="data && setupSteps.length"
      class="nb-card bg-surface p-3"
      :open="setupDone < setupSteps.length"
    >
      <summary class="cursor-pointer text-xs font-bold uppercase tracking-wide opacity-70">
        🧭 {{ t('shell.home.setup.title', { done: setupDone, total: setupSteps.length }) }}
      </summary>
      <ol class="mt-2 space-y-1.5">
        <li v-for="(step, i) in setupSteps" :key="step.key" class="flex items-center gap-2">
          <span
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-ink text-[10px] font-bold"
            :class="step.done ? 'bg-brand-lime' : 'bg-paper'"
            aria-hidden="true"
          >
            {{ step.done ? '✓' : i + 1 }}
          </span>
          <span class="min-w-0 flex-1 text-xs" :class="{ 'opacity-60': step.done }">
            {{ t('shell.home.setup.' + step.key) }}
          </span>
          <button
            v-if="!step.done"
            class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
            @click="step.go()"
          >
            {{ t('shell.home.setup.go') }} ↗
          </button>
        </li>
      </ol>
    </details>

    <div v-if="data" class="grid gap-3 sm:grid-cols-2">
      <!-- Printer state -->
      <div class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('shell.home.printer') }}
        </p>
        <template v-if="data.printer.reachable">
          <span
            class="inline-block rounded-brutal border-2 border-ink px-2 py-0.5 text-sm font-bold"
            :class="stateBadge(data.printer.state).cls"
          >
            {{ stateBadge(data.printer.state).text }}
          </span>
          <template v-if="data.printer.state === 'printing' || data.printer.state === 'paused'">
            <p class="truncate font-mono text-xs">{{ data.printer.filename }}</p>
            <div
              v-if="data.printer.progress != null"
              class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper"
            >
              <div
                class="h-full bg-brand-cyan"
                :style="{ width: Math.round((data.printer.progress ?? 0) * 100) + '%' }"
              ></div>
            </div>
            <p v-if="data.printer.progress != null" class="font-mono text-[11px] opacity-70">
              {{ Math.round((data.printer.progress ?? 0) * 100) }}%
            </p>
          </template>
        </template>
        <p v-else class="font-mono text-xs opacity-70">{{ t('shell.home.printerDown') }}</p>
      </div>

      <!-- Machine Doctor -->
      <div class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('shell.home.doctor') }}
        </p>
        <p class="text-xs opacity-70">{{ t('shell.home.doctorBody') }}</p>
        <button class="nb-btn bg-brand-cyan px-3 py-1 text-xs" @click="go('machine-doctor')">
          🩺 {{ t('shell.home.doctorScan') }}
        </button>
      </div>

      <!-- Firmware sync -->
      <div class="nb-card space-y-2 bg-surface p-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('shell.home.firmware') }}
          </p>
          <button
            class="nb-btn bg-surface px-1.5 py-0.5 text-[10px]"
            @click="go('firmware-upgrade', 'status')"
          >
            {{ t('shell.home.open') }} ↗
          </button>
        </div>
        <template v-if="data.firmware.available && data.firmware.mcus.length">
          <p class="font-mono text-[11px] opacity-70">
            {{ t('shell.home.host', { version: data.firmware.host_version ?? '—' }) }}
          </p>
          <ul class="space-y-1">
            <li v-for="m in data.firmware.mcus" :key="m.name">
              <button
                class="flex w-full items-center gap-2 rounded px-1 py-0.5 text-start font-mono text-[11px] hover:bg-ink/10"
                @click="openMcu(m.name)"
              >
                <span
                  class="shrink-0 font-bold"
                  :class="m.in_sync === false ? 'text-brand-red' : ''"
                  aria-hidden="true"
                  >{{ m.in_sync === false ? '⚠' : '✓' }}</span
                >
                <span class="min-w-0 flex-1 truncate">{{ m.name }}</span>
                <span class="shrink-0 opacity-60">{{ m.version ?? '—' }}</span>
              </button>
            </li>
          </ul>
        </template>
        <p v-else class="font-mono text-xs opacity-70">{{ t('shell.home.noData') }}</p>
      </div>

      <!-- Tuning -->
      <div class="nb-card space-y-2 bg-surface p-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('shell.home.tuning') }}
          </p>
          <button
            class="nb-btn bg-surface px-1.5 py-0.5 text-[10px]"
            @click="go('input-shaping', 'audit')"
          >
            {{ t('shell.home.open') }} ↗
          </button>
        </div>
        <template v-if="data.tuning.available && data.tuning.axes.length">
          <ul class="space-y-1 font-mono text-[11px]">
            <li v-for="a in data.tuning.axes" :key="a.axis" class="flex items-center gap-2">
              <span class="font-bold uppercase">{{ a.axis }}</span>
              <span>{{ a.shaper ?? '—' }}{{ a.freq != null ? ` @ ${a.freq} Hz` : '' }}</span>
              <span v-if="a.grade" class="nb-badge bg-brand-cyan">{{ a.grade }}</span>
              <span class="flex-1"></span>
              <span class="text-[10px] opacity-50">{{ a.created?.slice(0, 10) ?? '' }}</span>
            </li>
          </ul>
        </template>
        <p v-else class="text-xs opacity-70">{{ t('shell.home.noTuning') }}</p>
      </div>

      <!-- Hardware baseline -->
      <div class="nb-card space-y-2 bg-surface p-3 sm:col-span-2">
        <div class="flex items-center justify-between gap-2">
          <p class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('shell.home.hardware') }}
          </p>
          <button class="nb-btn bg-surface px-1.5 py-0.5 text-[10px]" @click="go('board-topology')">
            {{ t('shell.home.open') }} ↗
          </button>
        </div>
        <p v-if="!data.hardware.has_baseline" class="text-xs opacity-70">
          {{ t('shell.home.noBaseline') }}
        </p>
        <p v-else-if="!data.hardware.available" class="font-mono text-xs opacity-70">
          {{ t('shell.home.noData') }}
        </p>
        <p v-else-if="data.hardware.changes === 0" class="text-xs">
          <span class="font-bold text-brand-lime" aria-hidden="true">✓</span>
          {{ t('shell.home.hwUnchanged') }}
        </p>
        <p v-else class="text-xs">
          <span class="font-bold" aria-hidden="true">⚠</span>
          {{ t('shell.home.hwChanged', { n: data.hardware.changes }) }}
        </p>
      </div>
    </div>
  </div>
</template>
