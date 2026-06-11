<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { fetchLiveMacros, fetchMacros, simulateGcode } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { LiveMacro, MacroDef, SimResult } from './types'

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

const r1 = (n: number): number => Math.round(n * 10) / 10
const r2 = (n: number): number => Math.round(n * 100) / 100

const macroOptions = computed(() =>
  macros.value.map((m) => ({ value: m.id, label: m.name, sublabel: m.title })),
)
const selectedMacroDef = computed(
  () => macros.value.find((m) => m.id === selectedMacro.value) ?? null,
)

/** Map the simulated path into a flipped-Y SVG (units = mm; non-scaling strokes). Built from the
 *  segments so each drawn line carries its source G-code line (for hover-sync with the explainer). */
const pathView = computed(() => {
  const segs = result.value?.segments ?? []
  const b = result.value?.bounds
  if (!b || !segs.length) return null
  const pad = Math.max(1, (b.max_x - b.min_x + (b.max_y - b.min_y)) * 0.04)
  const w = b.max_x - b.min_x + pad * 2
  const h = b.max_y - b.min_y + pad * 2
  const sx = (x: number) => x - b.min_x + pad
  const sy = (y: number) => b.max_y - y + pad // flip Y (G-code Y up → SVG Y down)
  const lines = segs.map((s) => ({
    x1: sx(s.from[0]),
    y1: sy(s.from[1]),
    x2: sx(s.to[0]),
    y2: sy(s.to[1]),
    extruding: s.extruding,
    line: s.line,
  }))
  return { viewBox: `0 0 ${w || 1} ${h || 1}`, lines }
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
        const travel = s.dist > 1e-9 ? s.dist : Math.abs(s.e_delta)
        if (s.feedrate > 0 && travel > 0) cumTime += travel / (s.feedrate / 60)
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
    result.value = await simulateGcode(gcode.value, macroParams.value)
  } catch (e) {
    error.value = describeError(e)
    result.value = null
  } finally {
    simulating.value = false
  }
}

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

onMounted(() => {
  fetchMacros()
    .then((m) => (macros.value = m))
    .catch(() => {})
  fetchLiveMacros()
    .then((r) => {
      liveMacros.value = r.macros
      liveReachable.value = r.reachable
    })
    .catch(() => (liveReachable.value = false))
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
      <p v-if="error" class="font-mono text-[11px] text-brand-red">{{ error }}</p>
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
          <span class="nb-card bg-surface px-2 py-0.5">{{
            t('macroDesigner.result.time', { s: result.est_time_s })
          }}</span>
        </div>
        <p class="font-mono text-[10px] opacity-60">
          {{ t('macroDesigner.result.bounds') }}: X {{ result.bounds.min_x }}…{{
            result.bounds.max_x
          }}
          · Y {{ result.bounds.min_y }}…{{ result.bounds.max_y }} · Z {{ result.bounds.min_z }}…{{
            result.bounds.max_z
          }}
        </p>

        <!-- 2D path -->
        <div>
          <p class="mb-1 text-xs font-bold">{{ t('macroDesigner.path.title') }}</p>
          <svg
            v-if="pathView"
            :viewBox="pathView.viewBox"
            preserveAspectRatio="xMidYMid meet"
            class="nb-card h-64 w-full bg-paper"
            role="img"
            :aria-label="t('macroDesigner.path.title')"
          >
            <line
              v-for="(l, i) in pathView.lines"
              :key="i"
              :x1="l.x1"
              :y1="l.y1"
              :x2="l.x2"
              :y2="l.y2"
              :stroke="l.extruding ? 'rgb(var(--c-ink))' : 'rgb(var(--c-ink) / 0.35)'"
              :stroke-dasharray="l.extruding ? undefined : '1.5,1.5'"
              stroke-width="1"
              stroke-linecap="round"
              vector-effect="non-scaling-stroke"
              :class="{ 'seg-hi': hoveredLine === l.line }"
            />
          </svg>
          <p v-else class="font-mono text-[11px] opacity-60">
            {{ t('macroDesigner.path.noPath') }}
          </p>
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
