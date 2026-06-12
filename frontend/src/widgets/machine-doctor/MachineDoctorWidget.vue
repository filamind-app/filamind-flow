<script setup lang="ts">
/** Machine Doctor — one click, one graded report card for the whole printer.
 *
 *  Aggregates every read-only analyzer the app already ships (pin conflicts, driver values,
 *  disk-vs-live drift, config-project lint, firmware sync, hardware changes vs the saved
 *  baseline, install health) into an A–F grade with transparent scoring, and every finding
 *  carries a deep-link button into the widget that fixes it. Read-only: scanning never runs
 *  anything on the printer. */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { focusTopologyNode } from '@/widgets/board-topology/topologyFocus'
import { focusConfigSection } from '@/widgets/config-editor/configFocus'
import { focusStepper } from '@/widgets/motor-drivers/driverFocus'

import { fetchDoctorScan } from './api'
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
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('machineDoctor.intro') }}</p>
      <button
        class="nb-btn shrink-0 bg-brand-cyan px-3 py-1.5 text-xs"
        :disabled="scanning"
        @click="scan"
      >
        {{ scanning ? t('machineDoctor.scanning') : t('machineDoctor.rescan') }}
      </button>
    </div>

    <p v-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>
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
          <p class="font-bold">{{ t('machineDoctor.scoreLine', { score: report.score }) }}</p>
          <p class="font-mono text-[11px] opacity-70">
            {{ t('machineDoctor.counts', { errors: report.errors, warnings: report.warnings }) }}
          </p>
          <p class="text-[10px] opacity-50">{{ t('machineDoctor.scoreHint') }}</p>
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
