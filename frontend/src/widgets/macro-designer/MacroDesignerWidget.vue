<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { fetchMacros, simulateGcode } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { MacroDef, SimResult } from './types'

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

const macroOptions = computed(() =>
  macros.value.map((m) => ({ value: m.id, label: m.name, sublabel: m.title })),
)
const selectedMacroDef = computed(
  () => macros.value.find((m) => m.id === selectedMacro.value) ?? null,
)

/** Map the simulated path into a flipped-Y SVG (units = mm; non-scaling strokes). */
const pathView = computed(() => {
  const pts = result.value?.path2d ?? []
  const b = result.value?.bounds
  if (!b || pts.length < 2) return null
  const pad = Math.max(1, (b.max_x - b.min_x + (b.max_y - b.min_y)) * 0.04)
  const w = b.max_x - b.min_x + pad * 2
  const h = b.max_y - b.min_y + pad * 2
  const sx = (x: number) => x - b.min_x + pad
  const sy = (y: number) => b.max_y - y + pad // flip Y (G-code Y up → SVG Y down)
  const lines = []
  for (let i = 1; i < pts.length; i++) {
    lines.push({
      x1: sx(pts[i - 1].x),
      y1: sy(pts[i - 1].y),
      x2: sx(pts[i].x),
      y2: sy(pts[i].y),
      extruding: pts[i].extruding,
    })
  }
  return { viewBox: `0 0 ${w || 1} ${h || 1}`, lines }
})

async function doSimulate(): Promise<void> {
  simulating.value = true
  error.value = null
  try {
    result.value = await simulateGcode(gcode.value)
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

onMounted(() => {
  fetchMacros()
    .then((m) => (macros.value = m))
    .catch(() => {})
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
