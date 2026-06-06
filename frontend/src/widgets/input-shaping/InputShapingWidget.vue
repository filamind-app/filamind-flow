<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'

import CsvSourceChooser from './CsvSourceChooser.vue'
import DiagnosticIllo from './DiagnosticIllo.vue'
import GuidedTune from './GuidedTune.vue'
import HelpNote from './HelpNote.vue'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import ResonanceCompare from './ResonanceCompare.vue'
import ResonanceFromPrinter from './ResonanceFromPrinter.vue'
import { analyzeResonance, analyzeResonanceFile, listArchive, saveConfigToArchive } from './api'
import {
  buildShaperRecord,
  loadLocalAudit,
  mergeAudit,
  migrateLegacyHistory,
  recordAudit,
  withAuditTrends,
  type AuditRecord,
} from './audit'
import { buildResponseChart } from './chart'
import { inputShaperConfig } from './config'
import { diagnose, diagnoseAxes, type DiagnosticLevel } from './diagnose'
import { gradeAnalysis, type Rating } from './grade'
import { addHistory } from './history'
import type { ArchiveRun, ShaperAnalysis } from './types'

const { t } = useI18n({ useScope: 'global' })

/** The widget's top-level views. Guided is the default landing view; Analyze and Live
 *  are the manual / on-printer paths; Audit aggregates every past result. */
type Mode = 'guided' | 'analyze' | 'live' | 'audit'
const mode = ref<Mode>('guided')
const TABS = computed<{ id: Mode; label: string }[]>(() => [
  { id: 'guided', label: t('inputShaping.widget.tabGuided') },
  { id: 'analyze', label: t('inputShaping.widget.tabAnalyze') },
  { id: 'live', label: t('inputShaping.widget.tabLive') },
  { id: 'audit', label: t('inputShaping.widget.tabHistory') },
])
const analysis = ref<ShaperAnalysis | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const copied = ref(false)
const savedToArchive = ref(false)
const showAdvanced = ref(false)
const showCompare = ref(false)
const showFactors = ref(false)
const chooserRef = ref<InstanceType<typeof CsvSourceChooser> | null>(null)
const localAudit = ref<AuditRecord[]>([])
const archiveRuns = ref<ArchiveRun[]>([])

/** Advanced calibration knobs (kept as strings for the inputs; blank = default). */
const params = reactive({ maxFreq: '200', scv: '5', maxSmoothing: '', dampingRatio: '' })

/** Results accumulated per axis ('x' / 'y') or 'generic' (no axis), so an X and a
 *  Y capture combine into a single config block. */
const byAxis = reactive<Record<string, ShaperAnalysis>>({})

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'
const numClass = `${inputClass} w-16 font-mono`

const captured = computed(() => ['generic', 'x', 'y'].filter((k) => byAxis[k]))
const configText = computed(() => {
  const list = ['x', 'y', 'generic'].map((k) => byAxis[k]).filter(Boolean) as ShaperAnalysis[]
  return list.length ? inputShaperConfig(list) : ''
})
const chart = computed(() => (analysis.value ? buildResponseChart(analysis.value) : null))
const rec = computed(() => analysis.value?.shapers.find((s) => s.recommended) ?? null)
const grade = computed(() => (analysis.value ? gradeAnalysis(analysis.value) : null))
const diagnostics = computed(() => {
  if (!analysis.value) return []
  const list = diagnose(analysis.value)
  // Once both axes are captured, flag a big X-vs-Y stiffness mismatch.
  if (byAxis.x && byAxis.y) {
    const cross = diagnoseAxes(byAxis.x, byAxis.y)
    if (cross) list.push(cross)
  }
  return list
})

/** The aggregated audit: local records (shaper + the live tools) merged with the
 *  on-host archive, newest-first, shaper runs annotated with their grade trend. */
const auditView = computed(() => withAuditTrends(mergeAudit(localAudit.value, archiveRuns.value)))

async function loadAudit(): Promise<void> {
  migrateLegacyHistory()
  localAudit.value = loadLocalAudit()
  try {
    archiveRuns.value = (await listArchive()).runs
  } catch {
    /* the archive lives on the printer host — fine to be unavailable off-host */
  }
}
onMounted(loadAudit)

function trendArrow(trend: 'up' | 'down' | 'same' | 'none'): string {
  return trend === 'up' ? '▲' : trend === 'down' ? '▼' : trend === 'same' ? '=' : ''
}
function trendClass(trend: 'up' | 'down' | 'same' | 'none'): string {
  return trend === 'up' ? 'text-brand-lime' : trend === 'down' ? 'text-brand-red' : 'opacity-30'
}

function gradeBg(letter: string): string {
  if (letter === 'A' || letter === 'B') return 'bg-brand-lime'
  if (letter === 'C') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
function dotClass(rating: Rating): string {
  return rating === 'good' ? 'bg-brand-lime' : rating === 'ok' ? 'bg-brand-yellow' : 'bg-brand-red'
}
function diagClass(level: DiagnosticLevel): string {
  if (level === 'good') return 'bg-brand-lime'
  if (level === 'warn') return 'bg-brand-yellow'
  return 'bg-brand-red text-surface'
}
/** Keeps the peak label inside the plot — flips to the left of the marker near
 *  the right edge. */
function peakLabelX(x: number, width: number): number {
  return x > width * 0.78 ? x - 3 : x + 3
}
function fmtDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
function num(value: string, fallback: number): number {
  const n = Number(value)
  return value.trim() !== '' && Number.isFinite(n) ? n : fallback
}

/** Files an analysis into the displayed state, the combined config, and history. */
function applyResult(result: ShaperAnalysis): void {
  analysis.value = result
  // A generic capture replaces any per-axis ones and vice versa, so the config
  // block never mixes `shaper_type` with `shaper_type_x`.
  const key = result.axis === 'x' || result.axis === 'y' ? result.axis : 'generic'
  if (key === 'generic') {
    delete byAxis.x
    delete byAxis.y
  } else {
    delete byAxis.generic
  }
  byAxis[key] = result
  if (result.recommended_shaper && result.recommended_freq != null) {
    const g = gradeAnalysis(result)
    // Keep the legacy grade-history (additive) and record an audit entry.
    addHistory({
      at: new Date().toISOString(),
      axis: result.axis,
      shaper: result.recommended_shaper,
      freq: result.recommended_freq,
      grade: g.letter,
      score: g.score,
    })
    localAudit.value = recordAudit(buildShaperRecord(result, g))
  }
}

/** Analyses whichever source the chooser picked — an upload or a host/archive file —
 *  applying the shared advanced params either way, then files the result. */
async function onSourceAnalyze(req: {
  kind: 'upload' | 'host'
  file?: File
  path?: string
  axis: string | null
}): Promise<void> {
  if (busy.value) return
  error.value = null
  busy.value = true
  try {
    const opts = {
      axis: req.axis ?? undefined,
      maxFreq: num(params.maxFreq, 200),
      scv: num(params.scv, 5),
      maxSmoothing: params.maxSmoothing.trim() ? Number(params.maxSmoothing) : undefined,
      dampingRatio: params.dampingRatio.trim() ? Number(params.dampingRatio) : undefined,
    }
    const result =
      req.kind === 'upload' && req.file
        ? await analyzeResonance(req.file, opts)
        : await analyzeResonanceFile(req.path ?? '', opts)
    applyResult(result)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('inputShaping.widget.errAnalysisFailed')
  } finally {
    busy.value = false
  }
}

/** A live tool (noise / belts / axes-map / sustain / vibrations) reported a result —
 *  file it into the audit so every test type is aggregated in one place. */
function onRecorded(record: Omit<AuditRecord, 'id' | 'source'>): void {
  localAudit.value = recordAudit(record)
}

function clearResults(): void {
  analysis.value = null
  for (const key of Object.keys(byAxis)) delete byAxis[key]
}

async function copyConfig(): Promise<void> {
  if (!configText.value) return
  try {
    await navigator.clipboard.writeText(configText.value)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1500)
  } catch {
    error.value = t('inputShaping.widget.errCopyFailed')
  }
}

/** Saves the generated config to the on-host archive (a deletable historical record). */
async function saveConfig(): Promise<void> {
  if (!configText.value) return
  try {
    await saveConfigToArchive(configText.value, analysis.value?.axis ?? null, {
      shaper: analysis.value?.recommended_shaper ?? null,
      freq: analysis.value?.recommended_freq ?? null,
    })
    savedToArchive.value = true
    window.setTimeout(() => (savedToArchive.value = false), 1500)
    chooserRef.value?.refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('inputShaping.widget.errSaveFailed')
  }
}
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <i18n-t
        keypath="inputShaping.widget.intro"
        tag="p"
        scope="global"
        class="min-w-0 flex-1 font-mono text-[11px] opacity-70"
      >
        <template #guided><strong>🧭 Guided</strong></template>
        <template #analyze><strong>📈 Analyze</strong></template>
        <template #csv><code>.csv</code></template>
        <template #live><strong>🔴 Live tools</strong></template>
        <template #history><strong>🕘 History</strong></template>
      </i18n-t>
      <HelpDrawer
        namespace="inputShaping"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('inputShaping.help.guide')"
        :title="t('inputShaping.help.guideTitle')"
        :close-label="t('inputShaping.help.close')"
      />
    </div>

    <!-- Mode strip: one view at a time (Guided is the default landing view). -->
    <WidgetTabs v-model="mode" :tabs="TABS" />

    <!-- Pinned "config ready" bar (#116): the widget's payoff is otherwise the last element, so
         after a capture it's surfaced at the top of every working view with one-tap Copy/Archive. -->
    <div
      v-if="configText && mode !== 'audit'"
      class="flex flex-wrap items-center gap-2 rounded-brutal border-2 border-ink bg-brand-lime px-2 py-1 text-[11px]"
    >
      <span class="font-bold uppercase tracking-wide">{{ t('inputShaping.widget.cfgReady') }}</span>
      <span v-for="k in captured" :key="k" class="nb-badge bg-surface text-[10px]">{{
        k === 'generic' ? 'X+Y' : k.toUpperCase()
      }}</span>
      <span class="flex-1"></span>
      <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyConfig">
        {{ copied ? t('inputShaping.widget.copied') : t('inputShaping.widget.copy') }}
      </button>
      <button class="nb-btn px-2 py-0.5 text-[11px]" @click="saveConfig">
        {{ savedToArchive ? t('inputShaping.widget.saved') : t('inputShaping.widget.archive') }}
      </button>
    </div>

    <!-- GUIDED — kept mounted (v-show) so an in-progress wizard survives a tab switch. -->
    <div v-show="mode === 'guided'" class="space-y-2">
      <HelpNote topic="guided" />
      <GuidedTune @analyzed="applyResult" @exit="mode = 'analyze'" />
    </div>

    <!-- ANALYZE — pick a CSV (upload or from the host / archive), tune the knobs, compare. -->
    <div v-show="mode === 'analyze'" class="space-y-3">
      <CsvSourceChooser ref="chooserRef" :busy="busy" @analyze="onSourceAnalyze" />
      <div class="flex flex-wrap items-center gap-2">
        <button class="nb-btn px-2 py-1 text-[11px]" @click="showAdvanced = !showAdvanced">
          {{ t('inputShaping.widget.advanced') }}
        </button>
        <button class="nb-btn px-2 py-1 text-[11px]" @click="showCompare = !showCompare">
          {{ t('inputShaping.widget.compareCsvs') }}
        </button>
      </div>

      <div
        v-if="showAdvanced"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1.5 font-mono text-[11px]"
      >
        <label class="flex items-center gap-1"
          >max_freq <input v-model="params.maxFreq" :class="numClass"
        /></label>
        <label class="flex items-center gap-1"
          >scv <input v-model="params.scv" :class="numClass"
        /></label>
        <label class="flex items-center gap-1"
          >max_smoothing <input v-model="params.maxSmoothing" placeholder="—" :class="numClass"
        /></label>
        <label class="flex items-center gap-1"
          >damping_ratio <input v-model="params.dampingRatio" placeholder="—" :class="numClass"
        /></label>
        <span class="opacity-50">{{ t('inputShaping.widget.blankDefault') }}</span>
      </div>

      <ResonanceCompare v-if="showCompare" />
    </div>

    <!-- LIVE TOOLS — on-printer captures. Kept mounted (v-show) so results persist. -->
    <ResonanceFromPrinter v-show="mode === 'live'" @analyzed="applyResult" @recorded="onRecorded" />

    <!-- AUDIT — every past result (local + the on-host archive), per-property. -->
    <div
      v-show="mode === 'audit'"
      class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2"
    >
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wide">{{
          t('inputShaping.widget.auditTitle')
        }}</span>
        <button class="nb-btn px-2 py-0.5 text-[11px]" @click="loadAudit">
          {{ t('inputShaping.widget.refresh') }}
        </button>
      </div>
      <HelpNote topic="history" />
      <p v-if="!auditView.length" class="font-mono text-[11px] opacity-60">
        {{ t('inputShaping.widget.auditEmpty') }}
      </p>
      <div
        v-for="r in auditView"
        :key="r.id"
        class="space-y-1 rounded-brutal border-2 border-ink p-2"
      >
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="nb-badge bg-brand-yellow text-[10px]">{{ r.kind }}</span>
          <span v-if="r.axis" class="nb-badge bg-brand-cyan text-[10px]">{{
            r.axis.toUpperCase()
          }}</span>
          <span v-if="r.grade" class="nb-badge text-[10px]" :class="gradeBg(r.grade.letter)">{{
            r.grade.letter
          }}</span>
          <span
            v-if="r.trend !== 'none'"
            :class="trendClass(r.trend)"
            :title="
              t('inputShaping.widget.trendTitle', {
                score: r.grade?.score,
                axis: (r.axis ?? 'xy').toUpperCase(),
              })
            "
            >{{ trendArrow(r.trend) }}</span
          >
          <span class="font-mono text-[10px] opacity-50">{{ fmtDate(r.at) }}</span>
          <span class="flex-1"></span>
          <span
            class="nb-badge text-[10px]"
            :class="r.source === 'archive' ? 'bg-brand-lime' : 'bg-surface'"
            >{{
              r.source === 'archive'
                ? t('inputShaping.widget.sourceSaved')
                : t('inputShaping.widget.sourceLocal')
            }}</span
          >
        </div>
        <p v-if="r.verdict" class="text-[11px] leading-snug opacity-80">{{ r.verdict }}</p>
        <div
          v-if="r.fields.length"
          class="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[10px]"
        >
          <div v-for="(f, i) in r.fields" :key="i" class="flex justify-between gap-2">
            <span class="shrink-0 opacity-60">{{ f.label }}</span>
            <span class="min-w-0 truncate text-end font-bold">{{ f.value }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <!-- Shared result view — the recommended shaper, A–F grade, frequency chart and shaper table.
         Shown in EVERY working view (Analyze, Live, and Guided — which otherwise shows only
         per-step gate badges, so the full result was previously invisible there). #116 -->
    <template v-if="analysis && mode !== 'audit'">
      <div
        v-if="analysis.recommended_shaper"
        class="flex flex-wrap items-center gap-2 rounded-brutal border-2 border-ink bg-brand-lime px-3 py-2"
      >
        <span class="text-xs font-bold uppercase tracking-wide">{{
          t('inputShaping.widget.recommended')
        }}</span>
        <span class="font-mono text-base font-bold">{{
          analysis.recommended_shaper.toUpperCase()
        }}</span>
        <span class="font-mono text-sm">{{
          t('inputShaping.widget.recFreq', { v: analysis.recommended_freq?.toFixed(1) })
        }}</span>
        <span v-if="analysis.axis" class="nb-badge bg-surface">
          {{ t('inputShaping.widget.recAxis', { v: analysis.axis.toUpperCase() }) }}
        </span>
        <span v-if="rec" class="nb-badge bg-surface font-mono">
          {{ t('inputShaping.widget.recAccel', { v: rec.max_accel.toFixed(0) }) }}
        </span>
      </div>
      <div v-else class="nb-badge bg-brand-yellow">{{ t('inputShaping.widget.noShaper') }}</div>

      <!-- Measurement quality grade (A–F) with a factor breakdown. -->
      <div
        v-if="grade"
        class="flex items-center gap-3 rounded-brutal border-2 border-ink bg-paper px-3 py-2"
      >
        <span
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-brutal border-2 border-ink font-mono text-2xl font-black"
          :class="gradeBg(grade.letter)"
          >{{ grade.letter }}</span
        >
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2">
            <span class="text-xs font-bold uppercase tracking-wide">{{
              t('inputShaping.widget.measurementQuality')
            }}</span>
            <span class="font-mono text-[11px] opacity-70">{{
              t('inputShaping.widget.scoreOutOf', { v: grade.score })
            }}</span>
          </div>
          <p class="text-[11px] leading-tight">{{ grade.verdict }}</p>
        </div>
        <button
          v-if="grade.factors.length > 1"
          class="nb-btn px-2 py-0.5 text-[11px]"
          @click="showFactors = !showFactors"
        >
          {{ showFactors ? t('inputShaping.widget.hide') : t('inputShaping.widget.details') }}
        </button>
      </div>

      <HelpNote topic="grade" />

      <div
        v-if="grade && showFactors"
        class="space-y-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1.5"
      >
        <div
          v-for="f in grade.factors"
          :key="f.label"
          class="flex flex-wrap items-center gap-x-2 text-[11px]"
        >
          <span class="inline-block h-2 w-2 rounded-full" :class="dotClass(f.rating)" />
          <span class="font-medium">{{ f.label }}</span>
          <span class="font-mono opacity-70">{{ f.value }}</span>
          <span class="text-[10px] opacity-50">— {{ f.note }}</span>
        </div>
      </div>

      <!-- Diagnostics + fixes, each with an illustration. -->
      <div v-if="diagnostics.length" class="space-y-1.5">
        <div
          v-for="(d, i) in diagnostics"
          :key="i"
          class="flex items-start gap-2 rounded-brutal border-2 border-ink px-2 py-1.5"
          :class="diagClass(d.level)"
        >
          <DiagnosticIllo :illo="d.illo" class="mt-0.5 h-7 w-7 shrink-0" />
          <div class="min-w-0 flex-1 space-y-0.5">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-[11px] font-bold">{{ d.title }}</span>
              <span class="nb-badge bg-surface font-mono text-[10px] text-ink">{{ d.detail }}</span>
            </div>
            <p class="text-[11px] leading-snug">{{ d.advice }}</p>
          </div>
        </div>
      </div>

      <!-- Frequency response: PSD curves (front) over shaper-reduction curves (behind). -->
      <div v-if="chart && chart.psd.length" class="space-y-1">
        <svg
          :viewBox="`0 0 ${chart.width} ${chart.height}`"
          class="w-full rounded-brutal border-2 border-ink bg-paper"
          role="img"
          :aria-label="t('inputShaping.widget.chartAria')"
        >
          <line
            v-for="tick in chart.xTicks"
            :key="'g' + tick.label"
            :x1="tick.x"
            :x2="tick.x"
            :y1="6"
            :y2="chart.height - 12"
            stroke="#111111"
            stroke-opacity="0.12"
            stroke-width="0.5"
          />
          <!-- Noise floor (median PSD) — anything near it is just noise. -->
          <line
            v-if="chart.noiseY != null"
            :x1="4"
            :x2="chart.width - 4"
            :y1="chart.noiseY"
            :y2="chart.noiseY"
            stroke="#111111"
            stroke-opacity="0.3"
            stroke-width="0.5"
            stroke-dasharray="3 2"
          />
          <polyline
            v-for="s in chart.shapers"
            :key="'sh' + s.name"
            :points="s.points"
            fill="none"
            :stroke="s.color"
            stroke-width="0.8"
            :stroke-dasharray="s.dashed ? '2 2' : ''"
          />
          <polyline
            v-for="s in chart.psd"
            :key="'psd' + s.name"
            :points="s.points"
            fill="none"
            :stroke="s.color"
            stroke-width="1"
          />
          <!-- Dominant resonance peak. -->
          <g v-if="chart.peak">
            <line
              :x1="chart.peak.x"
              :x2="chart.peak.x"
              :y1="6"
              :y2="chart.height - 12"
              stroke="#ff5247"
              stroke-width="0.6"
              stroke-dasharray="2 1.5"
            />
            <circle
              :cx="chart.peak.x"
              :cy="chart.peak.y"
              r="2.2"
              fill="#ff5247"
              stroke="#111111"
              stroke-width="0.5"
            />
            <text
              :x="peakLabelX(chart.peak.x, chart.width)"
              :y="11"
              font-size="6.5"
              font-weight="bold"
              fill="#ff5247"
              :text-anchor="chart.peak.x > chart.width * 0.78 ? 'end' : 'start'"
            >
              {{ t('inputShaping.widget.peakLabel', { v: chart.peak.label }) }}
            </text>
          </g>
          <text
            v-for="tick in chart.xTicks"
            :key="'t' + tick.label"
            :x="tick.x"
            :y="chart.height - 2"
            font-size="6"
            fill="#111111"
            fill-opacity="0.6"
            text-anchor="middle"
          >
            {{ tick.label }}
          </text>
        </svg>
        <div class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px]">
          <span v-for="s in chart.psd" :key="'lg' + s.name" class="flex items-center gap-1">
            <span class="inline-block h-2 w-3 rounded-sm" :style="{ background: s.color }" />
            {{ s.name }}
          </span>
          <span class="flex items-center gap-1 opacity-70">
            <span class="inline-block h-0 w-3 border-t-2" style="border-color: #ff5c8a" />
            {{ t('inputShaping.widget.legendRecommended') }}
          </span>
          <span class="flex items-center gap-1" style="color: #ff5247">{{
            t('inputShaping.widget.legendPeak')
          }}</span>
          <span class="opacity-50">{{ t('inputShaping.widget.legendAxisHint') }}</span>
        </div>
        <HelpNote topic="chart" />
      </div>

      <div class="space-y-1">
        <div
          class="grid grid-cols-[1fr_auto_auto_auto_auto] gap-3 border-b-2 border-ink pb-0.5 font-mono text-[11px] font-bold uppercase"
        >
          <span>{{ t('inputShaping.widget.colShaper') }}</span>
          <span class="text-end">{{ t('inputShaping.widget.colFreq') }}</span>
          <span class="text-end">{{ t('inputShaping.widget.colVibr') }}</span>
          <span class="text-end">{{ t('inputShaping.widget.colSmooth') }}</span>
          <span class="text-end">{{ t('inputShaping.widget.colAccel') }}</span>
        </div>
        <div
          v-for="s in analysis.shapers"
          :key="s.name"
          class="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 rounded px-1 font-mono text-[11px]"
          :class="s.recommended ? 'bg-brand-lime/50 font-bold' : ''"
        >
          <span>{{ s.name.toUpperCase() }}</span>
          <span class="text-end">{{
            t('inputShaping.widget.rowFreq', { v: s.freq.toFixed(1) })
          }}</span>
          <span class="text-end">{{
            t('inputShaping.widget.rowVibr', { v: s.vibrations_pct.toFixed(1) })
          }}</span>
          <span class="text-end">{{ s.smoothing.toFixed(3) }}</span>
          <span class="text-end">{{
            t('inputShaping.widget.rowAccel', { v: s.max_accel.toFixed(0) })
          }}</span>
        </div>
      </div>

      <HelpNote topic="shapers" />
    </template>

    <!-- Combined config block (accumulates across the X and Y captures) — shown in
         any working view (Guided / Analyze / Live), hidden while reviewing History. -->
    <div v-if="configText && mode !== 'audit'" class="space-y-1">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-bold uppercase tracking-wide">{{
          t('inputShaping.widget.printerCfg')
        }}</span>
        <span class="flex items-center gap-1 font-mono text-[10px] opacity-70">
          <span v-for="k in captured" :key="k" class="nb-badge bg-brand-cyan">{{
            k === 'generic' ? 'X+Y' : k.toUpperCase()
          }}</span>
        </span>
        <span class="flex-1"></span>
        <button class="nb-btn px-2 py-0.5 text-[11px]" @click="copyConfig">
          {{ copied ? t('inputShaping.widget.copied') : t('inputShaping.widget.copy') }}
        </button>
        <button class="nb-btn px-2 py-0.5 text-[11px]" @click="saveConfig">
          {{ savedToArchive ? t('inputShaping.widget.saved') : t('inputShaping.widget.archive') }}
        </button>
        <button class="nb-btn px-2 py-0.5 text-[11px]" @click="clearResults">
          {{ t('inputShaping.widget.clear') }}
        </button>
      </div>
      <pre
        class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
        >{{ configText }}</pre
      >
      <i18n-t
        keypath="inputShaping.widget.pasteHint"
        tag="p"
        scope="global"
        class="text-[10px] italic opacity-50"
      >
        <template #cfg><code>printer.cfg</code></template>
      </i18n-t>
      <HelpNote topic="config" />
    </div>
  </div>
</template>
