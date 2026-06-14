<script setup lang="ts">
/** Machine Doctor — one click, one graded report card for the whole printer.
 *
 *  Aggregates every read-only analyzer the app already ships (pin conflicts, driver values,
 *  disk-vs-live drift, config-project lint, firmware sync, hardware changes vs the saved
 *  baseline, install health) into an A–F grade with transparent scoring, and every finding
 *  carries a deep-link button into the widget that fixes it. Read-only: scanning never runs
 *  anything on the printer. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { focusTopologyNode } from '@/widgets/board-topology/topologyFocus'
import { focusConfigSection } from '@/widgets/config-editor/configFocus'
import { focusStepper } from '@/widgets/motor-drivers/driverFocus'

import { fetchDoctorScan } from './api'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import HelpIllo from './HelpIllo.vue'
import type { DoctorFinding, DoctorLink, DoctorReport } from './types'

const { t, te } = useI18n({ useScope: 'global' })
const { go } = useNav()

const report = ref<DoctorReport | null>(null)
const scanning = ref(false)
const error = ref<string | null>(null)

async function scan(): Promise<void> {
  scanning.value = true
  error.value = null
  try {
    report.value = await fetchDoctorScan()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    scanning.value = false
  }
}
onMounted(() => void scan())

const GRADE_BG: Record<string, string> = {
  A: 'bg-brand-lime',
  B: 'bg-brand-cyan',
  C: 'bg-brand-yellow',
  D: 'bg-brand-pink',
  F: 'bg-brand-red',
}

function findingText(f: DoctorFinding): string {
  const key = `machineDoctor.finding.${f.code}`
  return te(key) ? t(key, f.params as Record<string, unknown>) : f.code
}

function linkLabel(link: DoctorLink): string {
  const key = `machineDoctor.link.${link.kind}`
  return te(key) ? t(key) : t('machineDoctor.link.widget')
}

function follow(link: DoctorLink): void {
  switch (link.kind) {
    case 'config_section':
      focusConfigSection(link.value)
      go('config-editor')
      break
    case 'config_file':
      focusConfigSection('', link.value)
      go('config-editor')
      break
    case 'stepper':
      focusStepper(link.value)
      go('motor-drivers')
      break
    case 'topology_node':
      focusTopologyNode(link.value)
      go('board-topology')
      break
    default:
      go(link.value, link.tab)
  }
}

const STATUS_ICON: Record<string, string> = { ok: '✓', warn: '⚠', fail: '✕', unknown: '?' }
const STATUS_BG: Record<string, string> = {
  ok: 'bg-brand-lime/20',
  warn: 'bg-brand-yellow/20',
  fail: 'bg-brand-red/10',
  unknown: 'bg-ink/5',
}

const PILLAR_BAR: Record<string, string> = {
  ok: 'bg-brand-lime',
  warn: 'bg-brand-yellow',
  fail: 'bg-brand-red',
  unknown: 'bg-ink/20',
}

function pillarLabel(key: string): string {
  const k = `machineDoctor.pillar.${key}`
  return te(k) ? t(k) : key
}

/** The headline verdict, with the weakest pillar's key resolved to its localized label. */
const assessmentText = computed(() => {
  const a = report.value?.assessment
  if (!a) return ''
  const key = `machineDoctor.assessment.${a.code}`
  if (!te(key)) return ''
  const pillar = a.params.pillar ? pillarLabel(String(a.params.pillar)) : ''
  return t(key, { ...a.params, pillar } as Record<string, unknown>)
})

const hasStats = computed(() => {
  const s = report.value?.stats
  return !!(s && (s.max_flow?.max_flow_mm3s != null || s.tuning?.length || s.firmware))
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('machineDoctor.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="machineDoctor"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="machineDoctor.help.steps"
          :button-label="t('machineDoctor.help.guide')"
          :title="t('machineDoctor.help.guideTitle')"
          :close-label="t('machineDoctor.help.close')"
          :steps-title="t('machineDoctor.help.howToRead')"
        />
        <button class="nb-btn bg-brand-cyan px-3 py-1.5 text-xs" :disabled="scanning" @click="scan">
          {{ scanning ? t('machineDoctor.scanning') : t('machineDoctor.rescan') }}
        </button>
      </div>
    </div>

    <div
      v-if="error"
      role="alert"
      class="nb-card flex items-start justify-between gap-2 bg-brand-red/10 p-2 font-mono text-xs"
    >
      <span class="min-w-0 break-words">{{ error }}</span>
      <ReportErrorButton :error="error" />
    </div>
    <p v-else-if="scanning && !report" class="font-mono text-xs opacity-70">
      {{ t('machineDoctor.scanning') }}
    </p>

    <template v-if="report">
      <!-- Grade hero -->
      <div class="nb-card flex items-center gap-4 bg-surface p-3">
        <span
          class="flex h-16 w-16 shrink-0 items-center justify-center rounded-brutal border-3 border-ink font-display text-4xl font-bold text-ink"
          :class="GRADE_BG[report.grade] ?? 'bg-ink/10'"
        >
          {{ report.grade }}
        </span>
        <div class="min-w-0 space-y-0.5">
          <p v-if="assessmentText" class="font-bold">{{ assessmentText }}</p>
          <p class="font-mono text-[11px] opacity-70">
            {{ t('machineDoctor.scoreLine', { score: report.score }) }} ·
            {{ t('machineDoctor.counts', { errors: report.errors, warnings: report.warnings }) }}
          </p>
          <p class="text-[11px] opacity-50">{{ t('machineDoctor.scoreHint') }}</p>
        </div>
      </div>

      <!-- Health pillars -->
      <div v-if="report.pillars?.length" class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold">{{ t('machineDoctor.pillars.title') }}</p>
        <div v-for="p in report.pillars" :key="p.key" class="space-y-1">
          <div class="flex items-center justify-between gap-2 text-[11px]">
            <span class="min-w-0 truncate">
              {{ t('machineDoctor.pillar.' + p.key) }}
              <span class="opacity-50">· {{ Math.round(p.weight * 100) }}%</span>
            </span>
            <span class="shrink-0 font-mono" :class="p.score === null ? 'opacity-50' : 'font-bold'">
              {{ p.score === null ? t('machineDoctor.pillars.notMeasured') : Math.round(p.score) }}
            </span>
          </div>
          <div class="h-2 overflow-hidden rounded-full border border-ink bg-paper">
            <div
              class="h-full"
              :class="PILLAR_BAR[p.status] ?? 'bg-ink/20'"
              :style="{ width: (p.score ?? 0) + '%' }"
            ></div>
          </div>
        </div>
      </div>

      <!-- Running services -->
      <div v-if="report.services?.units?.length" class="nb-card space-y-1 bg-surface p-3">
        <p class="text-xs font-bold">{{ t('machineDoctor.services.title') }}</p>
        <ul class="space-y-1">
          <li
            v-for="s in report.services.units"
            :key="s.name"
            class="flex items-center gap-2 text-[11px]"
          >
            <span
              class="shrink-0 font-bold"
              :class="s.active ? 'text-brand-lime' : 'text-brand-red'"
              aria-hidden="true"
            >
              {{ s.active ? '✓' : '✕' }}
            </span>
            <span class="min-w-0 flex-1 truncate font-mono">{{ s.name }}</span>
            <span class="shrink-0 font-mono text-[11px] opacity-60">
              {{
                s.sub_state ||
                (s.active
                  ? t('machineDoctor.services.active')
                  : t('machineDoctor.services.inactive'))
              }}
            </span>
          </li>
        </ul>
      </div>

      <!-- At a glance (cross-widget stats) -->
      <div v-if="hasStats" class="nb-card space-y-1.5 bg-surface p-3">
        <p class="text-xs font-bold">{{ t('machineDoctor.stats.title') }}</p>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <div
            v-if="report.stats.max_flow?.max_flow_mm3s != null"
            class="rounded-brutal border-2 border-ink bg-paper p-1.5"
          >
            <div class="text-[11px] opacity-60">{{ t('machineDoctor.stats.maxFlow') }}</div>
            <div class="font-mono text-xs font-bold">
              {{ report.stats.max_flow.max_flow_mm3s }} mm³/s
            </div>
          </div>
          <div
            v-for="ax in report.stats.tuning || []"
            :key="ax.axis"
            class="rounded-brutal border-2 border-ink bg-paper p-1.5"
          >
            <div class="text-[11px] opacity-60">
              {{ t('machineDoctor.stats.tuningAxis', { axis: ax.axis.toUpperCase() }) }}
            </div>
            <div class="font-mono text-xs font-bold">
              {{ (ax.shaper || '—').toUpperCase()
              }}{{ ax.freq != null ? ' · ' + ax.freq.toFixed(1) + ' Hz' : '' }}
              <span v-if="ax.grade">· {{ ax.grade }}</span>
            </div>
          </div>
          <div
            v-if="report.stats.firmware"
            class="rounded-brutal border-2 border-ink bg-paper p-1.5"
          >
            <div class="text-[11px] opacity-60">{{ t('machineDoctor.stats.firmware') }}</div>
            <div class="font-mono text-xs font-bold">
              {{
                report.stats.firmware.out_of_sync
                  ? t('machineDoctor.stats.outOfSync', { n: report.stats.firmware.out_of_sync })
                  : t('machineDoctor.stats.allSynced')
              }}
            </div>
          </div>
        </div>
      </div>

      <!-- Categories -->
      <ul class="space-y-2">
        <li
          v-for="cat in report.categories"
          :key="cat.key"
          class="nb-card p-2"
          :class="STATUS_BG[cat.status] ?? 'bg-surface'"
        >
          <div class="flex items-center gap-2">
            <span class="font-bold" aria-hidden="true">{{ STATUS_ICON[cat.status] ?? '·' }}</span>
            <span class="text-xs font-bold">{{ t('machineDoctor.category.' + cat.key) }}</span>
            <span class="flex-1"></span>
            <span class="font-mono text-[10px] opacity-60">
              {{ t('machineDoctor.status.' + cat.status) }}
            </span>
          </div>

          <ul v-if="cat.findings.length" class="mt-1.5 space-y-1 text-[11px]">
            <li v-for="(f, i) in cat.findings" :key="i" class="flex flex-wrap items-start gap-1.5">
              <span
                class="shrink-0 rounded px-1 text-[10px] font-bold"
                :class="
                  f.level === 'error'
                    ? 'bg-brand-red text-paper'
                    : f.level === 'warning'
                      ? 'bg-brand-yellow text-ink'
                      : 'bg-ink/10'
                "
              >
                {{ f.level === 'error' ? '✕' : f.level === 'warning' ? '⚠' : 'ℹ' }}
              </span>
              <span class="min-w-0 flex-1">{{ findingText(f) }}</span>
              <button
                v-if="f.link"
                class="nb-btn shrink-0 bg-surface px-1.5 py-0.5 text-[10px]"
                @click="follow(f.link)"
              >
                {{ linkLabel(f.link) }} ↗
              </button>
            </li>
          </ul>
          <p v-else-if="cat.status === 'ok'" class="mt-1 text-[11px] opacity-60">
            {{ t('machineDoctor.allClear') }}
          </p>
          <p v-else-if="cat.status === 'unknown'" class="mt-1 text-[11px] opacity-60">
            {{ t('machineDoctor.notChecked') }}
          </p>
        </li>
      </ul>
    </template>
  </div>
</template>
