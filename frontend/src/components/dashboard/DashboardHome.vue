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
import { fetchDoctorScan } from '@/widgets/machine-doctor/api'
import type { DoctorReport } from '@/widgets/machine-doctor/types'

const { t, te } = useI18n({ useScope: 'global' })
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
interface JournalEvent {
  at: string
  kind: string
  params: Record<string, string | number | null>
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
// Machine Doctor summary, surfaced right on the home (full detail lives in the widget). Fetched
// lazily alongside the overview — its own loading/error state, so it never blocks the other tiles.
const doctor = ref<DoctorReport | null>(null)
const doctorLoading = ref(true)
async function loadDoctor(): Promise<void> {
  doctorLoading.value = true
  try {
    doctor.value = await fetchDoctorScan()
  } catch {
    doctor.value = null
  } finally {
    doctorLoading.value = false
  }
}
const GRADE_BG: Record<string, string> = {
  A: 'bg-brand-lime',
  B: 'bg-brand-cyan',
  C: 'bg-brand-yellow',
  D: 'bg-brand-pink',
  F: 'bg-brand-red',
}
function doctorPillarLabel(key: string): string {
  const k = `machineDoctor.pillar.${key}`
  return te(k) ? t(k) : key
}
const doctorAssessment = computed(() => {
  const a = doctor.value?.assessment
  if (!a) return ''
  const key = `machineDoctor.assessment.${a.code}`
  if (!te(key)) return ''
  const pillar = a.params.pillar ? doctorPillarLabel(String(a.params.pillar)) : ''
  return t(key, { ...a.params, pillar } as Record<string, unknown>)
})

const journal = ref<JournalEvent[]>([])
async function loadJournal(): Promise<void> {
  try {
    const { backendUrl } = resolveEndpoints()
    const response = await fetch(`${backendUrl}/api/journal`)
    if (!response.ok) throw new Error(String(response.status))
    journal.value = ((await response.json()) as { events: JournalEvent[] }).events
  } catch {
    journal.value = []
  }
}
function journalText(e: JournalEvent): string {
  if (e.kind === 'flash') {
    return t('shell.home.journal.flash', {
      board: e.params.board ?? '?',
      version: e.params.version ?? '?',
    })
  }
  if (e.kind === 'config_save') {
    return t('shell.home.journal.configSave', { file: e.params.file ?? '?' })
  }
  return t('shell.home.journal.tuning', {
    kind: String(e.params.run_kind ?? ''),
    axis: e.params.axis ? String(e.params.axis).toUpperCase() : '—',
  })
}
const JOURNAL_ICON: Record<string, string> = { flash: '🔧', config_save: '📝', tuning: '📈' }

function refresh(): void {
  void load()
  void loadJournal()
  void loadDoctor()
}
onMounted(refresh)

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
      <button class="nb-btn bg-surface px-2 py-1 text-xs" :disabled="loading" @click="refresh">
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

      <!-- Machine Doctor — live grade + assessment + Max-Flow, with the full scan one tap away -->
      <div class="nb-card space-y-2 bg-surface p-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('shell.home.doctor') }}
          </p>
          <button class="nb-btn bg-surface px-1.5 py-0.5 text-[11px]" @click="go('machine-doctor')">
            {{ t('shell.home.open') }} ↗
          </button>
        </div>
        <template v-if="doctor">
          <div class="flex items-center gap-3">
            <span
              class="flex h-11 w-11 shrink-0 items-center justify-center rounded-brutal border-3 border-ink font-display text-2xl font-bold text-ink"
              :class="GRADE_BG[doctor.grade] ?? 'bg-ink/10'"
            >
              {{ doctor.grade }}
            </span>
            <div class="min-w-0">
              <p v-if="doctorAssessment" class="text-xs font-bold">{{ doctorAssessment }}</p>
              <p class="font-mono text-[11px] opacity-70">
                {{ t('machineDoctor.scoreLine', { score: doctor.score }) }} ·
                {{
                  t('machineDoctor.counts', { errors: doctor.errors, warnings: doctor.warnings })
                }}
              </p>
            </div>
          </div>
          <p
            v-if="doctor.stats?.max_flow?.max_flow_mm3s != null"
            class="flex items-center gap-1.5 font-mono text-[11px]"
          >
            <span class="opacity-60">{{ t('machineDoctor.stats.maxFlow') }}:</span>
            <span class="font-bold">{{ doctor.stats.max_flow.max_flow_mm3s }} mm³/s</span>
          </p>
        </template>
        <p v-else-if="doctorLoading" class="font-mono text-xs opacity-70">
          {{ t('machineDoctor.scanning') }}
        </p>
        <template v-else>
          <p class="text-xs opacity-70">{{ t('shell.home.doctorBody') }}</p>
          <button class="nb-btn bg-brand-cyan px-3 py-1 text-xs" @click="go('machine-doctor')">
            🩺 {{ t('shell.home.doctorScan') }}
          </button>
        </template>
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

      <!-- Recent activity: the machine's merged journal (flashes / config saves / tuning) -->
      <div class="nb-card space-y-2 bg-surface p-3 sm:col-span-2">
        <p class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('shell.home.journal.title') }}
        </p>
        <p v-if="!journal.length" class="text-xs opacity-60">
          {{ t('shell.home.journal.empty') }}
        </p>
        <ul v-else class="space-y-1">
          <li
            v-for="(e, i) in journal.slice(0, 8)"
            :key="i"
            class="flex items-center gap-2 font-mono text-[11px]"
          >
            <span aria-hidden="true">{{ JOURNAL_ICON[e.kind] ?? '·' }}</span>
            <span class="min-w-0 flex-1 truncate">{{ journalText(e) }}</span>
            <span class="shrink-0 text-[10px] opacity-50">{{
              e.at.slice(0, 16).replace('T', ' ')
            }}</span>
          </li>
        </ul>
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
