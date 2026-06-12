<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { fetchConfigFiles } from '@/widgets/config-editor/api'
import { fetchHotends } from '@/widgets/max-flow/api'

import {
  appendScaffold,
  fetchLimits,
  fetchLiveMacros,
  fetchMacros,
  fetchScaffold,
  simulateGcode,
} from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type {
  LiveMacro,
  MachineLimits,
  MacroDef,
  ScaffoldNote,
  ScaffoldResult,
  SimResult,
  SimViolation,
} from './types'

const SAMPLE = [
  'G28',
  'G90',
  'M83',
  'G1 X20 Y20 F6000',
  'G1 X80 Y20 E3 F1200',
  'G1 X80 Y80 E3',
  'G1 X20 Y80 E3',
  'G1 X20 Y20 E3',
].join('\n')

const { t } = useI18n({ useScope: 'global' })

const gcode = ref(SAMPLE)
const result = ref<SimResult | null>(null)
const simulating = ref(false)
const error = ref<string | null>(null)
const macros = ref<MacroDef[]>([])
const selectedMacro = ref<string | null>(null)
const hoveredLine = ref<number | null>(null)

// Import the printer's OWN installed [gcode_macro] definitions, with editable discovered params.
const liveMacros = ref<LiveMacro[]>([])
const liveReachable = ref(true)
const selectedLive = ref<string | null>(null)
const macroParams = ref<Record<string, string>>({})
const liveOptions = computed(() =>
  liveMacros.value.map((m) => ({ value: m.name, label: m.name, sublabel: m.description })),
)
const paramKeys = computed(() => Object.keys(macroParams.value))

// The printer's real build envelope + speed cap — grounds the simulation in THIS machine's bounds.
const machineLimits = ref<MachineLimits | null>(null)

function violationMsg(v: SimViolation): string {
  if (v.kind === 'out_of_bounds' && Array.isArray(v.limit)) {
    return t('macroDesigner.limits.oob', {
      line: v.line,
      axis: v.axis,
      value: v.value,
      min: v.limit[0],
      max: v.limit[1],
    })
  }
  if (v.kind === 'over_speed') {
    return t('macroDesigner.limits.overSpeed', { line: v.line, value: v.value, limit: v.limit })
  }
  return `${t('macroDesigner.timeline.line')} ${v.line}: ${v.kind}`
}

const r1 = (n: number): number => Math.round(n * 10) / 10
const r2 = (n: number): number => Math.round(n * 100) / 100

const macroOptions = computed(() =>
  macros.value.map((m) => ({ value: m.id, label: m.name, sublabel: m.title })),
)
const selectedMacroDef = computed(
  () => macros.value.find((m) => m.id === selectedMacro.value) ?? null,
)

// Flow check: compare each printing move's volumetric flow against a hotend's real ceiling
// from the catalog — a macro that silently over-runs the melt zone shows up BEFORE it prints.
const hotends = ref<{ name: string; expected_max_flow_mm3s?: number | null }[]>([])
const flowHotend = ref<string | null>(null)
const flowDiameter = ref(1.75)
const hotendFlowOptions = computed(() =>
  hotends.value
    .filter((h) => typeof h.expected_max_flow_mm3s === 'number')
    .map((h) => ({ value: h.name, label: `${h.name} (${h.expected_max_flow_mm3s} mm³/s)` })),
)
const flowCeiling = computed(() => {
  const row = hotends.value.find((h) => h.name === flowHotend.value)
  return typeof row?.expected_max_flow_mm3s === 'number' ? row.expected_max_flow_mm3s : null
})
/** Printing moves whose volumetric flow exceeds the selected hotend's ceiling. */
const flowViolations = computed(() => {
  const ceiling = flowCeiling.value
  const r = result.value
  if (ceiling == null || !r) return []
  const area = Math.PI * (flowDiameter.value / 2) ** 2 // filament cross-section, mm²
  const out: { line: number; flow: number }[] = []
  for (const s of r.segments) {
    if (!s.extruding || s.extrude_rate == null) continue
    const flow = s.extrude_rate * area
    if (flow > ceiling + 1e-6) out.push({ line: s.line, flow: Math.round(flow * 10) / 10 })
  }
  return out
})

/** Path recolor mode: a flat draw, a speed heatmap, or an extrusion-rate heatmap. */
const colorBy = ref<'none' | 'speed' | 'extrude'>('none')

/** Blue (slow / low) → red (fast / high) for a normalised value in [0, 1]. */
function heatColor(tNorm: number): string {
  const hue = Math.round(220 - 220 * Math.min(1, Math.max(0, tNorm)))
  return `hsl(${hue}, 80%, 48%)`
}

/** Map the simulated path into a flipped-Y SVG (units = mm; non-scaling strokes). Built from the
 *  segments so each drawn line carries its source G-code line (for hover-sync with the explainer). */
const pathView = computed(() => {
  const segs = result.value?.segments ?? []
  const b = result.value?.bounds
  if (!b || !segs.length) return null
  const lim = result.value?.limits // the envelope the sim was run against (null when unreachable)
  let minX = b.min_x
  let maxX = b.max_x
  let minY = b.min_y
  let maxY = b.max_y
  if (lim) {
    minX = Math.min(minX, lim.min[0])
    maxX = Math.max(maxX, lim.max[0])
    minY = Math.min(minY, lim.min[1])
    maxY = Math.max(maxY, lim.max[1])
  }
  const pad = Math.max(1, (maxX - minX + (maxY - minY)) * 0.04)
  const w = maxX - minX + pad * 2
  const h = maxY - minY + pad * 2
  const sx = (x: number) => x - minX + pad
  const sy = (y: number) => maxY - y + pad // flip Y (G-code Y up → SVG Y down)
  const env = lim
    ? {
        x: sx(lim.min[0]),
        y: sy(lim.max[1]),
        w: lim.max[0] - lim.min[0],
        h: lim.max[1] - lim.min[1],
      }
    : null
  // Heatmap normalisation: speed colours every move; extrusion colours only extruding moves.
  const mode = colorBy.value
  const valueOf = (s: (typeof segs)[number]): number =>
    mode === 'speed' ? (s.v_mm_s ?? s.feedrate / 60) : (s.extrude_rate ?? 0)
  const heatSegs = mode === 'none' ? [] : segs.filter((s) => mode === 'speed' || s.extruding)
  const vals = heatSegs.map(valueOf)
  const vmin = vals.length ? Math.min(...vals) : 0
  const vmax = vals.length ? Math.max(...vals) : 0
  const heatOf = (s: (typeof segs)[number]): string | null => {
    if (mode === 'none') return null
    if (mode === 'extrude' && !s.extruding) return null
    const t = vmax > vmin ? (valueOf(s) - vmin) / (vmax - vmin) : 0.5
    return heatColor(t)
  }
  const lines = segs.map((s) => ({
    x1: sx(s.from[0]),
    y1: sy(s.from[1]),
    x2: sx(s.to[0]),
    y2: sy(s.to[1]),
    extruding: s.extruding,
    line: s.line,
    violation: !!(s.out_of_bounds || s.over_speed),
    heat: heatOf(s),
  }))
  const legend =
    mode === 'none' || !vals.length ? null : { mode, min: Math.round(vmin), max: Math.round(vmax) }
  return { viewBox: `0 0 ${w || 1} ${h || 1}`, lines, env, legend }
})

type StepKind = 'travel' | 'print' | 'retract' | 'prime' | 'mode' | 'home' | 'set' | 'none'
interface ExplainStep {
  line: number
  glyph: string
  kind: StepKind
  text: string
  posAbs: boolean
  isMove: boolean
  cumDist: number
  cumExtrude: number
  cumTime: number
}

/** A plain-language, step-by-step walkthrough built from the simulation (no backend) — each command
 *  in English, the running positioning mode, and cumulative travel / extrusion / time. */
const explainSteps = computed<ExplainStep[]>(() => {
  const r = result.value
  if (!r) return []
  const segByLine = new Map(r.segments.map((s) => [s.line, s]))
  let posAbs = true
  let cumDist = 0
  let cumExtrude = 0
  let cumTime = 0
  const out: ExplainStep[] = []
  for (const e of r.timeline) {
    let glyph = '·'
    let kind: StepKind = 'none'
    let text = ''
    let isMove = false
    if (e.action === 'move') {
      const s = segByLine.get(e.line)
      if (s) {
        isMove = true
        cumDist += s.dist
        if (s.e_delta > 0) cumExtrude += s.e_delta
        if (s.time_s != null) {
          cumTime += s.time_s // accel-aware per-segment time from the simulator
        } else {
          const travel = s.dist > 1e-9 ? s.dist : Math.abs(s.e_delta)
          if (s.feedrate > 0 && travel > 0) cumTime += travel / (s.feedrate / 60)
        }
        const f = Math.round(s.feedrate)
        if (s.extruding) {
          kind = 'print'
          glyph = '🖊'
          text = t('macroDesigner.explain.print', {
            e: r2(s.e_delta),
            d: r1(s.dist),
            x: r1(s.to[0]),
            y: r1(s.to[1]),
            f,
          })
        } else if (s.dist > 1e-9) {
          kind = 'travel'
          glyph = '↗'
          text = t('macroDesigner.explain.travel', { x: r1(s.to[0]), y: r1(s.to[1]), f })
        } else if (s.e_delta < 0) {
          kind = 'retract'
          glyph = '⟲'
          text = t('macroDesigner.explain.retract', { e: r2(-s.e_delta) })
        } else if (s.e_delta > 0) {
          kind = 'prime'
          glyph = '⟳'
          text = t('macroDesigner.explain.prime', { e: r2(s.e_delta) })
        } else {
          text = t('macroDesigner.explain.noMove')
        }
      }
    } else if (e.action === 'absolute XYZ') {
      posAbs = true
      kind = 'mode'
      glyph = '⊞'
      text = t('macroDesigner.explain.absXYZ')
    } else if (e.action === 'relative XYZ') {
      posAbs = false
      kind = 'mode'
      glyph = '⊟'
      text = t('macroDesigner.explain.relXYZ')
    } else if (e.action === 'absolute E') {
      kind = 'mode'
      glyph = '⊞'
      text = t('macroDesigner.explain.absE')
    } else if (e.action === 'relative E') {
      kind = 'mode'
      glyph = '⊟'
      text = t('macroDesigner.explain.relE')
    } else if (e.action === 'set position') {
      kind = 'set'
      glyph = '⌖'
      text = t('macroDesigner.explain.setPos')
    } else if (e.action === 'home') {
      kind = 'home'
      glyph = '⌂'
      text = t('macroDesigner.explain.home')
    }
    out.push({
      line: e.line,
      glyph,
      kind,
      text,
      posAbs,
      isMove,
      cumDist: r1(cumDist),
      cumExtrude: r2(cumExtrude),
      cumTime: r1(cumTime),
    })
  }
  return out
})

async function doSimulate(): Promise<void> {
  simulating.value = true
  error.value = null
  try {
    result.value = await simulateGcode(gcode.value, macroParams.value, machineLimits.value)
  } catch (e) {
    error.value = describeError(e)
    result.value = null
  } finally {
    simulating.value = false
  }
}

// A/B compare: simulate a second program (B) and diff it against the current result (A).
const gcodeB = ref('')
const resultB = ref<SimResult | null>(null)
const comparingB = ref(false)
const errorB = ref<string | null>(null)

async function compareB(): Promise<void> {
  comparingB.value = true
  errorB.value = null
  try {
    resultB.value = await simulateGcode(gcodeB.value, macroParams.value, machineLimits.value)
  } catch (e) {
    errorB.value = describeError(e)
    resultB.value = null
  } finally {
    comparingB.value = false
  }
}
/** Seed B with the current A program so the user starts from a copy to tweak. */
function copyAtoB(): void {
  gcodeB.value = gcode.value
}

/** Overlay both paths in one shared viewBox (A solid, B dashed). */
const compareView = computed(() => {
  const a = result.value
  const b = resultB.value
  if (!a || !b || !a.segments.length || !b.segments.length) return null
  let minX = Math.min(a.bounds.min_x, b.bounds.min_x)
  let maxX = Math.max(a.bounds.max_x, b.bounds.max_x)
  let minY = Math.min(a.bounds.min_y, b.bounds.min_y)
  let maxY = Math.max(a.bounds.max_y, b.bounds.max_y)
  const lim = a.limits ?? b.limits
  if (lim) {
    minX = Math.min(minX, lim.min[0])
    maxX = Math.max(maxX, lim.max[0])
    minY = Math.min(minY, lim.min[1])
    maxY = Math.max(maxY, lim.max[1])
  }
  const pad = Math.max(1, (maxX - minX + (maxY - minY)) * 0.04)
  const w = maxX - minX + pad * 2
  const h = maxY - minY + pad * 2
  const sx = (x: number): number => x - minX + pad
  const sy = (y: number): number => maxY - y + pad
  const proj = (r: SimResult) =>
    r.segments.map((s) => ({
      x1: sx(s.from[0]),
      y1: sy(s.from[1]),
      x2: sx(s.to[0]),
      y2: sy(s.to[1]),
      extruding: s.extruding,
    }))
  return { viewBox: `0 0 ${w || 1} ${h || 1}`, a: proj(a), b: proj(b) }
})

/** Per-stat A / B / Δ rows. */
const statsDelta = computed(() => {
  const a = result.value
  const b = resultB.value
  if (!a || !b) return null
  const row = (key: string, av: number, bv: number) => ({
    key,
    a: av,
    b: bv,
    delta: Math.round((bv - av) * 100) / 100,
  })
  return [
    row('moves', a.move_count, b.move_count),
    row('distance', a.total_distance_mm, b.total_distance_mm),
    row('extrude', a.total_extrude_mm, b.total_extrude_mm),
    row('time', a.est_time_s, b.est_time_s),
  ]
})

/** Which lint rules fire in A only, B only, or both. */
const lintDelta = computed(() => {
  const a = result.value
  const b = resultB.value
  if (!a || !b) return null
  const ar = new Set(a.lint.map((f) => f.rule))
  const br = new Set(b.lint.map((f) => f.rule))
  return {
    both: [...ar].filter((r) => br.has(r)),
    aOnly: [...ar].filter((r) => !br.has(r)),
    bOnly: [...br].filter((r) => !ar.has(r)),
  }
})

function insertMacro(macro: MacroDef): void {
  const block = macro.expands_to.join('\n')
  gcode.value = gcode.value.trimEnd() ? `${gcode.value.trimEnd()}\n${block}` : block
}

/** Load one of the printer's installed macros into the editor (with its params) and simulate it. */
function loadLiveMacro(name: string | null): void {
  selectedLive.value = name
  const def = liveMacros.value.find((m) => m.name === name)
  if (!def) return
  gcode.value = def.gcode
  macroParams.value = { ...def.params }
  void doSimulate()
}

// Scaffold generator: build START_PRINT / END_PRINT tailored to this printer, review, then write
// to a config file behind the existing gated save (backup + refuse-while-printing) — first write.
const scaffold = ref<ScaffoldResult | null>(null)
const scaffoldLoading = ref(false)
const scaffoldErr = ref<string | null>(null)
const configFiles = ref<{ value: string; label: string }[]>([])
const scaffoldTarget = ref<string | null>('printer.cfg')
const confirmAppend = ref(false)
const appendBusy = ref(false)
const appendMsg = ref<string | null>(null)
const appendErr = ref<string | null>(null)

async function genScaffold(): Promise<void> {
  scaffoldLoading.value = true
  scaffoldErr.value = null
  appendMsg.value = null
  try {
    scaffold.value = await fetchScaffold()
  } catch (e) {
    scaffoldErr.value = describeError(e)
    scaffold.value = null
  } finally {
    scaffoldLoading.value = false
  }
}
function scaffoldNote(n: ScaffoldNote): string {
  return t('macroDesigner.scaffold.note.' + n.key, n.params)
}
/** Drop one generated macro into the editor for review / simulation. */
function loadScaffold(which: 'start' | 'end'): void {
  if (!scaffold.value) return
  gcode.value = scaffold.value[which]
  void doSimulate()
}
async function appendScaffoldToConfig(): Promise<void> {
  if (!scaffold.value || !scaffoldTarget.value) return
  appendBusy.value = true
  appendErr.value = null
  appendMsg.value = null
  try {
    const block = `${scaffold.value.start}\n${scaffold.value.end}`
    const r = await appendScaffold(scaffoldTarget.value, block)
    appendMsg.value = r.backup
      ? t('macroDesigner.scaffold.savedBackup', { file: scaffoldTarget.value, backup: r.backup })
      : t('macroDesigner.scaffold.saved', { file: scaffoldTarget.value })
    confirmAppend.value = false
  } catch (e) {
    appendErr.value = describeError(e)
  } finally {
    appendBusy.value = false
  }
}

onMounted(() => {
  fetchHotends()
    .then((rows) => (hotends.value = rows))
    .catch(() => {})
  fetchConfigFiles()
    .then((r) => {
      configFiles.value = r.files.map((f) => ({ value: f.path, label: f.path }))
    })
    .catch(() => {})
  fetchMacros()
    .then((m) => (macros.value = m))
    .catch(() => {})
  fetchLiveMacros()
    .then((r) => {
      liveMacros.value = r.macros
      liveReachable.value = r.reachable
    })
    .catch(() => (liveReachable.value = false))
  fetchLimits()
    .then((r) => (machineLimits.value = r.limits))
    .catch(() => (machineLimits.value = null))
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('macroDesigner.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="macroDesigner"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="macroDesigner.help.steps"
          :button-label="t('macroDesigner.help.guide')"
          :title="t('macroDesigner.help.guideTitle')"
          :close-label="t('macroDesigner.help.close')"
          :steps-title="t('macroDesigner.help.howToRead')"
        />
        <HelpIllo illo="path" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- Editor -->
    <div class="space-y-2">
      <span class="block text-xs font-bold">{{ t('macroDesigner.editor.label') }}</span>
      <textarea
        v-model="gcode"
        spellcheck="false"
        rows="8"
        class="nb-card w-full resize-y bg-surface p-2 font-mono text-[11px] leading-snug"
        :aria-label="t('macroDesigner.editor.label')"
      ></textarea>
      <!-- Editable macro params (discovered from the loaded macro's { params.X }) -->
      <div v-if="paramKeys.length" class="nb-card bg-surface p-2">
        <span class="mb-1 block text-xs font-bold">{{ t('macroDesigner.live.params') }}</span>
        <div class="flex flex-wrap gap-2">
          <label v-for="k in paramKeys" :key="k" class="text-[11px]">
            <span class="me-1 font-mono opacity-60">{{ k }}</span>
            <input
              v-model="macroParams[k]"
              spellcheck="false"
              class="w-24 rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 font-mono text-[11px]"
              :aria-label="k"
            />
          </label>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
          :disabled="simulating"
          @click="doSimulate"
        >
          {{
            simulating ? t('macroDesigner.editor.simulating') : t('macroDesigner.editor.simulate')
          }}
        </button>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="gcode = SAMPLE">
          {{ t('macroDesigner.editor.sample') }}
        </button>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="gcode = ''">
          {{ t('macroDesigner.editor.clear') }}
        </button>
      </div>
      <p v-if="error" role="alert" class="font-mono text-[11px] text-brand-red">{{ error }}</p>
    </div>

    <!-- From the printer: simulate your OWN installed macros -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <span class="block text-xs font-bold">{{ t('macroDesigner.live.label') }}</span>
      <p v-if="!liveReachable" class="font-mono text-[11px] opacity-60">
        {{ t('macroDesigner.live.unreachable') }}
      </p>
      <template v-else>
        <ComboSelect
          :model-value="selectedLive"
          :options="liveOptions"
          :placeholder="t('macroDesigner.live.placeholder')"
          clearable
          @update:model-value="loadLiveMacro"
        />
        <p class="font-mono text-[10px] opacity-60">
          {{ t('macroDesigner.live.hint', { n: liveMacros.length }) }}
        </p>
      </template>
    </div>

    <!-- Macro library -->
    <div class="nb-card space-y-2 bg-surface p-2">
      <span class="block text-xs font-bold">{{ t('macroDesigner.library.label') }}</span>
      <ComboSelect
        v-model="selectedMacro"
        :options="macroOptions"
        :placeholder="t('macroDesigner.library.placeholder')"
        clearable
      />
      <div v-if="selectedMacroDef" class="space-y-1 text-[11px]">
        <p class="opacity-80">{{ selectedMacroDef.description }}</p>
        <p class="font-mono opacity-60">
          {{
            t('macroDesigner.library.requires', {
              sections:
                selectedMacroDef.required_sections.join(', ') || t('macroDesigner.library.none'),
            })
          }}
        </p>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="insertMacro(selectedMacroDef)">
          {{ t('macroDesigner.library.insert') }}
        </button>
      </div>
    </div>

    <!-- Scaffold generator: a START_PRINT / END_PRINT tailored to this printer + gated write -->
    <details class="nb-card bg-surface p-2 text-[11px]">
      <summary class="cursor-pointer text-xs font-bold">
        {{ t('macroDesigner.scaffold.title') }}
      </summary>
      <div class="mt-2 space-y-2">
        <p class="text-[10px] opacity-70">{{ t('macroDesigner.scaffold.hint') }}</p>
        <button
          class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
          :disabled="scaffoldLoading"
          @click="genScaffold"
        >
          {{
            scaffoldLoading
              ? t('macroDesigner.scaffold.generating')
              : t('macroDesigner.scaffold.generate')
          }}
        </button>
        <p v-if="scaffoldErr" class="nb-card bg-brand-red/10 p-2 font-mono text-[10px]">
          {{ scaffoldErr }}
        </p>

        <template v-if="scaffold">
          <!-- What was tailored -->
          <ul v-if="scaffold.notes.length" class="space-y-0.5 text-[10px] opacity-80">
            <li v-for="(n, i) in scaffold.notes" :key="i">• {{ scaffoldNote(n) }}</li>
          </ul>

          <div class="grid gap-2 md:grid-cols-2">
            <div v-for="which in ['start', 'end'] as const" :key="which">
              <div class="mb-1 flex items-center gap-2">
                <span class="font-mono font-bold">{{
                  which === 'start' ? 'START_PRINT' : 'END_PRINT'
                }}</span>
                <button
                  class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
                  @click="loadScaffold(which)"
                >
                  {{ t('macroDesigner.scaffold.loadEditor') }}
                </button>
              </div>
              <pre
                class="max-h-48 overflow-auto rounded bg-ink/5 p-1 font-mono text-[10px] leading-snug"
                >{{ scaffold[which] }}</pre
              >
            </div>
          </div>

          <!-- Gated write to a config file -->
          <div class="nb-card bg-brand-yellow/15 p-2">
            <p class="mb-1 text-[11px] font-bold">{{ t('macroDesigner.scaffold.writeTitle') }}</p>
            <div class="flex flex-wrap items-end gap-2">
              <label class="min-w-[10rem] flex-1">
                <span class="mb-1 block text-[10px] opacity-70">{{
                  t('macroDesigner.scaffold.target')
                }}</span>
                <ComboSelect
                  v-model="scaffoldTarget"
                  :options="configFiles"
                  :placeholder="'printer.cfg'"
                />
              </label>
              <button
                v-if="!confirmAppend"
                class="nb-btn bg-surface px-3 py-1 text-xs"
                :disabled="!scaffoldTarget"
                @click="confirmAppend = true"
              >
                {{ t('macroDesigner.scaffold.append') }}
              </button>
              <template v-else>
                <button
                  class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
                  :disabled="appendBusy"
                  @click="appendScaffoldToConfig"
                >
                  {{
                    appendBusy
                      ? t('macroDesigner.scaffold.appending')
                      : t('macroDesigner.scaffold.confirm')
                  }}
                </button>
                <button class="nb-btn bg-surface px-3 py-1 text-xs" @click="confirmAppend = false">
                  {{ t('macroDesigner.scaffold.cancel') }}
                </button>
              </template>
            </div>
            <p class="mt-1 text-[10px] opacity-60">{{ t('macroDesigner.scaffold.writeNote') }}</p>
            <p v-if="appendMsg" class="mt-1 nb-card bg-brand-lime/20 p-1.5 text-[10px]">
              {{ appendMsg }}
            </p>
            <p v-if="appendErr" class="mt-1 nb-card bg-brand-red/10 p-1.5 font-mono text-[10px]">
              {{ appendErr }}
            </p>
          </div>
        </template>
      </div>
    </details>

    <!-- Result -->
    <template v-if="result">
      <div v-if="!result.move_count" class="font-mono text-xs opacity-70">
        {{ t('macroDesigner.result.empty') }}
      </div>
      <template v-else>
        <div class="flex flex-wrap gap-2 font-mono text-[11px]">
          <span class="nb-card bg-surface px-2 py-0.5">{{
            t('macroDesigner.result.moves', { count: result.move_count })
          }}</span>
          <span class="nb-card bg-surface px-2 py-0.5">{{
            t('macroDesigner.result.distance', { mm: result.total_distance_mm })
          }}</span>
          <span class="nb-card bg-surface px-2 py-0.5">{{
            t('macroDesigner.result.extrude', { mm: result.total_extrude_mm })
          }}</span>
          <span class="nb-card bg-surface px-2 py-0.5">
            {{ t('macroDesigner.result.time', { s: result.est_time_s }) }}
            <span class="opacity-60">{{
              result.time_model === 'accel'
                ? t('macroDesigner.result.timeAccel')
                : t('macroDesigner.result.timeConstant')
            }}</span>
          </span>
        </div>
        <p class="font-mono text-[10px] opacity-60">
          {{ t('macroDesigner.result.bounds') }}: X {{ result.bounds.min_x }}…{{
            result.bounds.max_x
          }}
          · Y {{ result.bounds.min_y }}…{{ result.bounds.max_y }} · Z {{ result.bounds.min_z }}…{{
            result.bounds.max_z
          }}
        </p>

        <!-- Out-of-bounds / over-speed violations (only when checked against the printer) -->
        <div v-if="result.violations.length" class="nb-card bg-brand-red/10 p-2">
          <p class="mb-1 text-xs font-bold">{{ t('macroDesigner.limits.title') }}</p>
          <ul class="space-y-0.5 font-mono text-[10px]">
            <li v-for="(v, i) in result.violations" :key="i">
              <span aria-hidden="true">⚠</span> {{ violationMsg(v) }}
            </li>
          </ul>
        </div>

        <!-- Macro linter findings (static safety checks) -->
        <div v-if="result.lint.length" class="nb-card bg-brand-yellow/15 p-2">
          <p class="mb-1 text-xs font-bold">
            {{ t('macroDesigner.lint.title', { n: result.lint.length }) }}
          </p>
          <ul class="space-y-1 text-[10px]">
            <li v-for="(f, i) in result.lint" :key="i" class="flex flex-wrap items-start gap-1">
              <span
                class="shrink-0 rounded px-1 font-bold"
                :class="
                  f.level === 'error' ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'
                "
              >
                {{ f.level === 'error' ? '✕' : '⚠' }}
              </span>
              <span class="min-w-0">
                <span v-if="f.line" class="font-mono opacity-60"
                  >{{ t('macroDesigner.timeline.line') }} {{ f.line }}: </span
                >{{ t('macroDesigner.lint.rule.' + f.rule + '.msg') }}
                <span class="opacity-70"
                  >→ {{ t('macroDesigner.lint.rule.' + f.rule + '.fix') }}</span
                >
              </span>
            </li>
          </ul>
        </div>

        <!-- Flow check: printing moves vs a hotend's real melt-zone ceiling (from the catalog) -->
        <details class="text-[11px]">
          <summary class="cursor-pointer font-bold">{{ t('macroDesigner.flow.title') }}</summary>
          <div class="mt-2 space-y-2">
            <p class="text-[10px] opacity-70">{{ t('macroDesigner.flow.hint') }}</p>
            <div class="flex flex-wrap items-end gap-2">
              <label class="min-w-[12rem] flex-1">
                <span class="mb-0.5 block text-[10px] opacity-70">{{
                  t('macroDesigner.flow.hotend')
                }}</span>
                <ComboSelect
                  v-model="flowHotend"
                  :options="hotendFlowOptions"
                  :placeholder="t('macroDesigner.flow.pick')"
                />
              </label>
              <label class="block w-24">
                <span class="mb-0.5 block text-[10px] opacity-70">{{
                  t('macroDesigner.flow.diameter')
                }}</span>
                <input
                  v-model.number="flowDiameter"
                  type="number"
                  step="0.05"
                  class="w-full rounded-brutal border-2 border-ink bg-surface px-1.5 py-1 font-mono text-[11px]"
                />
              </label>
            </div>
            <template v-if="flowCeiling != null">
              <p v-if="!flowViolations.length" class="text-[11px]">
                <span class="font-bold text-brand-lime" aria-hidden="true">✓</span>
                {{ t('macroDesigner.flow.ok', { ceiling: flowCeiling }) }}
              </p>
              <div v-else class="nb-card space-y-1 bg-brand-yellow/20 p-2">
                <p class="text-[11px] font-bold">
                  {{
                    t('macroDesigner.flow.overTitle', {
                      n: flowViolations.length,
                      ceiling: flowCeiling,
                    })
                  }}
                </p>
                <ul class="space-y-0.5 font-mono text-[10px]">
                  <li v-for="v in flowViolations.slice(0, 12)" :key="v.line">
                    {{ t('macroDesigner.flow.overLine', { line: v.line, flow: v.flow }) }}
                  </li>
                  <li v-if="flowViolations.length > 12" class="opacity-60">
                    +{{ flowViolations.length - 12 }}…
                  </li>
                </ul>
              </div>
            </template>
          </div>
        </details>

        <!-- 2D path -->
        <div>
          <div class="mb-1 flex flex-wrap items-center gap-2">
            <p class="text-xs font-bold">
              {{ t('macroDesigner.path.title')
              }}<span
                v-if="result.limits"
                class="ms-2 font-mono text-[10px] font-normal opacity-60"
              >
                {{
                  t('macroDesigner.limits.buildArea', {
                    x: result.limits.max[0] - result.limits.min[0],
                    y: result.limits.max[1] - result.limits.min[1],
                  })
                }}</span
              >
            </p>
            <span class="flex-1"></span>
            <label class="flex items-center gap-1 text-[10px] opacity-70">
              {{ t('macroDesigner.heat.colorBy') }}
              <select
                v-model="colorBy"
                class="rounded-brutal border border-ink bg-surface px-1 py-0.5 text-[10px]"
              >
                <option value="none">{{ t('macroDesigner.heat.none') }}</option>
                <option value="speed">{{ t('macroDesigner.heat.speed') }}</option>
                <option value="extrude">{{ t('macroDesigner.heat.extrude') }}</option>
              </select>
            </label>
          </div>
          <svg
            v-if="pathView"
            :viewBox="pathView.viewBox"
            preserveAspectRatio="xMidYMid meet"
            class="nb-card h-64 w-full bg-paper"
            role="img"
            :aria-label="t('macroDesigner.path.title')"
          >
            <!-- the printer's real build area (when known) -->
            <rect
              v-if="pathView.env"
              :x="pathView.env.x"
              :y="pathView.env.y"
              :width="pathView.env.w"
              :height="pathView.env.h"
              fill="none"
              stroke="rgb(var(--c-ink) / 0.4)"
              stroke-dasharray="2,2"
              stroke-width="0.7"
              vector-effect="non-scaling-stroke"
            />
            <line
              v-for="(l, i) in pathView.lines"
              :key="i"
              :x1="l.x1"
              :y1="l.y1"
              :x2="l.x2"
              :y2="l.y2"
              :stroke="
                l.violation
                  ? 'rgb(var(--c-brand-red))'
                  : l.heat
                    ? l.heat
                    : l.extruding
                      ? 'rgb(var(--c-ink))'
                      : 'rgb(var(--c-ink) / 0.35)'
              "
              :stroke-dasharray="l.extruding || l.violation || l.heat ? undefined : '1.5,1.5'"
              :stroke-width="l.violation ? 1.8 : 1"
              stroke-linecap="round"
              vector-effect="non-scaling-stroke"
              :class="{ 'seg-hi': hoveredLine === l.line }"
            />
          </svg>
          <p v-else class="font-mono text-[11px] opacity-60">
            {{ t('macroDesigner.path.noPath') }}
          </p>
          <!-- Heatmap legend (slow/low → fast/high) -->
          <div
            v-if="pathView && pathView.legend"
            class="mt-1 flex items-center gap-2 text-[10px] opacity-70"
          >
            <span>{{
              pathView.legend.mode === 'speed'
                ? t('macroDesigner.heat.legendSpeed')
                : t('macroDesigner.heat.legendExtrude')
            }}</span>
            <span class="font-mono">{{ pathView.legend.min }}</span>
            <span
              class="h-2 w-20 rounded"
              :style="{
                background:
                  'linear-gradient(to right, hsl(220,80%,48%), hsl(140,80%,48%), hsl(0,80%,48%))',
              }"
            ></span>
            <span class="font-mono">{{ pathView.legend.max }}</span>
          </div>
        </div>

        <!-- Warnings -->
        <div v-if="result.warnings.length" class="nb-card bg-brand-yellow/20 p-2">
          <p class="mb-1 text-xs font-bold">{{ t('macroDesigner.warnings.title') }}</p>
          <ul class="space-y-0.5 font-mono text-[10px] opacity-80">
            <li v-for="(w, i) in result.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- Explain (plain-language step-by-step walkthrough) -->
        <details class="text-[11px]" open>
          <summary class="cursor-pointer font-bold">{{ t('macroDesigner.explain.title') }}</summary>
          <ol class="mt-1 space-y-0.5">
            <li
              v-for="(st, i) in explainSteps"
              :key="i"
              class="flex items-start gap-2 rounded px-1 py-0.5"
              :class="[
                st.kind === 'mode' || st.kind === 'home' || st.kind === 'set'
                  ? 'bg-brand-cyan/15'
                  : '',
                hoveredLine === st.line && st.isMove ? 'bg-brand-pink/15' : '',
              ]"
              @mouseenter="hoveredLine = st.line"
              @mouseleave="hoveredLine = null"
            >
              <span class="w-7 shrink-0 text-end font-mono opacity-40">{{ st.line }}</span>
              <span aria-hidden="true" class="shrink-0">{{ st.glyph }}</span>
              <span class="min-w-0 flex-1">
                {{ st.text }}
                <span v-if="st.isMove" class="ms-1 font-mono text-[9px] opacity-50">
                  ({{
                    t('macroDesigner.explain.cum', {
                      d: st.cumDist,
                      e: st.cumExtrude,
                      s: st.cumTime,
                    })
                  }})
                </span>
              </span>
              <span class="shrink-0 font-mono text-[9px] opacity-40">
                {{ st.posAbs ? t('macroDesigner.explain.abs') : t('macroDesigner.explain.rel') }}
              </span>
            </li>
          </ol>
          <p v-if="result.warnings.length" class="mt-1 text-[10px] opacity-60">
            {{ t('macroDesigner.explain.note') }}
          </p>
        </details>

        <!-- Timeline -->
        <details class="text-[11px]">
          <summary class="cursor-pointer font-bold">
            {{ t('macroDesigner.timeline.title') }}
          </summary>
          <table class="mt-1 w-full border-collapse font-mono text-[10px]">
            <thead>
              <tr class="text-start opacity-60">
                <th class="pe-2 text-start">{{ t('macroDesigner.timeline.line') }}</th>
                <th class="pe-2 text-start">{{ t('macroDesigner.timeline.cmd') }}</th>
                <th class="text-start">{{ t('macroDesigner.timeline.action') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in result.timeline" :key="i">
                <td class="pe-2 opacity-60">{{ e.line }}</td>
                <td class="pe-2 font-bold">{{ e.cmd }}</td>
                <td>{{ e.action }}</td>
              </tr>
            </tbody>
          </table>
        </details>

        <!-- A/B compare: simulate a second program and diff it against this result -->
        <details class="text-[11px]">
          <summary class="cursor-pointer font-bold">{{ t('macroDesigner.compare.title') }}</summary>
          <div class="mt-2 space-y-2">
            <p class="text-[10px] opacity-70">{{ t('macroDesigner.compare.hint') }}</p>
            <div class="flex flex-wrap items-center gap-2">
              <button class="nb-btn bg-surface px-2 py-1 text-[11px]" @click="copyAtoB">
                {{ t('macroDesigner.compare.copyA') }}
              </button>
              <button
                class="nb-btn bg-brand-cyan px-2 py-1 text-[11px]"
                :disabled="comparingB || !gcodeB.trim()"
                @click="compareB"
              >
                {{
                  comparingB ? t('macroDesigner.compare.running') : t('macroDesigner.compare.run')
                }}
              </button>
            </div>
            <textarea
              v-model="gcodeB"
              spellcheck="false"
              rows="5"
              :placeholder="t('macroDesigner.compare.placeholder')"
              class="nb-card w-full resize-y bg-surface p-2 font-mono text-[11px] leading-snug"
              :aria-label="t('macroDesigner.compare.editorB')"
            ></textarea>
            <p v-if="errorB" class="nb-card bg-brand-red/10 p-2 font-mono text-[10px]">
              {{ errorB }}
            </p>

            <template v-if="resultB && statsDelta">
              <!-- Overlay: A solid, B dashed -->
              <svg
                v-if="compareView"
                :viewBox="compareView.viewBox"
                preserveAspectRatio="xMidYMid meet"
                class="nb-card h-56 w-full bg-paper"
                role="img"
                :aria-label="t('macroDesigner.compare.overlay')"
              >
                <line
                  v-for="(l, i) in compareView.a"
                  :key="'a' + i"
                  :x1="l.x1"
                  :y1="l.y1"
                  :x2="l.x2"
                  :y2="l.y2"
                  stroke="rgb(var(--c-ink))"
                  :stroke-dasharray="l.extruding ? undefined : '1.5,1.5'"
                  stroke-width="1"
                  stroke-linecap="round"
                  vector-effect="non-scaling-stroke"
                />
                <line
                  v-for="(l, i) in compareView.b"
                  :key="'b' + i"
                  :x1="l.x1"
                  :y1="l.y1"
                  :x2="l.x2"
                  :y2="l.y2"
                  stroke="rgb(var(--c-brand-pink))"
                  stroke-dasharray="3,2"
                  stroke-width="1.2"
                  stroke-linecap="round"
                  vector-effect="non-scaling-stroke"
                />
              </svg>
              <div class="flex gap-3 text-[10px]">
                <span
                  ><span class="me-1 inline-block h-1 w-3 bg-ink align-middle"></span
                  >{{ t('macroDesigner.compare.legendA') }}</span
                >
                <span
                  ><span class="me-1 inline-block h-1 w-3 bg-brand-pink align-middle"></span
                  >{{ t('macroDesigner.compare.legendB') }}</span
                >
              </div>

              <!-- Stats delta table -->
              <table class="w-full border-collapse font-mono text-[10px]">
                <thead>
                  <tr class="text-start opacity-60">
                    <th class="pe-2 text-start"></th>
                    <th class="pe-2 text-end">A</th>
                    <th class="pe-2 text-end">B</th>
                    <th class="text-end">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in statsDelta" :key="row.key">
                    <td class="pe-2 font-bold">{{ t('macroDesigner.compare.row.' + row.key) }}</td>
                    <td class="pe-2 text-end">{{ row.a }}</td>
                    <td class="pe-2 text-end">{{ row.b }}</td>
                    <td
                      class="text-end font-bold"
                      :class="
                        row.delta < 0
                          ? 'text-brand-lime'
                          : row.delta > 0
                            ? 'text-brand-red'
                            : 'opacity-50'
                      "
                    >
                      {{ row.delta > 0 ? '+' : '' }}{{ row.delta }}
                    </td>
                  </tr>
                </tbody>
              </table>

              <!-- Lint delta -->
              <div v-if="lintDelta" class="space-y-1">
                <p class="font-bold opacity-70">{{ t('macroDesigner.compare.lintDelta') }}</p>
                <p v-if="!lintDelta.aOnly.length && !lintDelta.bOnly.length" class="opacity-60">
                  {{ t('macroDesigner.compare.lintSame') }}
                </p>
                <div v-else class="flex flex-wrap gap-1">
                  <span
                    v-for="r in lintDelta.aOnly"
                    :key="'ao' + r"
                    class="rounded bg-ink/10 px-1"
                    :title="t('macroDesigner.compare.onlyA')"
                  >
                    A: {{ t('macroDesigner.lint.rule.' + r + '.msg') }}
                  </span>
                  <span
                    v-for="r in lintDelta.bOnly"
                    :key="'bo' + r"
                    class="rounded bg-brand-pink/30 px-1"
                    :title="t('macroDesigner.compare.onlyB')"
                  >
                    B: {{ t('macroDesigner.lint.rule.' + r + '.msg') }}
                  </span>
                </div>
              </div>
            </template>
          </div>
        </details>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* Hovering an Explain step lights up its drawn path segment (CSS beats the inline stroke attr). */
.seg-hi {
  stroke: rgb(var(--c-brand-pink)) !important;
  stroke-width: 2.5;
}
</style>
