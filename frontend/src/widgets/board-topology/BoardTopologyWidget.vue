<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { fetchFirmwareStatus } from '@/widgets/firmware-upgrade/api'
import type { McuFirmware } from '@/widgets/firmware-upgrade/types'
import { targetFor, useEntityFocus } from '@/widgets/hardware-browser/useEntityFocus'

import { clearBoardOverride, fetchDiff, fetchTopology, saveSnapshot, setBoardOverride } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import NodeInspector from './NodeInspector.vue'
import { pendingNode } from './topologyFocus'
import TopologyGraph from './TopologyGraph.vue'
import type { RelatedRef, Topology, TopologyChange, TopologyDiff } from './types'

const { t } = useI18n({ useScope: 'global' })
const { go } = useNav()
const { focusEntity } = useEntityFocus()

const topology = ref<Topology | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const fwMcus = ref<Record<string, McuFirmware>>({})

const view = ref<'logical' | 'physical'>('physical')
const selected = ref<string | null>(null)

// Inbound cross-widget focus: another widget asked us to select a node (by MCU section name,
// or 'host'). Applied once the topology is loaded; cleared after applying.
function applyTopologyFocus(): void {
  const wanted = pendingNode.value
  const topo = topology.value
  if (!wanted || !topo) return
  if (wanted === 'host') {
    if (topo.host) {
      selected.value = 'host'
      pendingNode.value = null
    }
    return
  }
  if (topo.mcus.some((m) => m.name === wanted)) {
    selected.value = 'mcu:' + wanted
    pendingNode.value = null
  }
}
watch(pendingNode, applyTopologyFocus)
watch(topology, applyTopologyFocus)
const overrideBusy = ref(false)

// Hardware snapshot / diff (detect a board swap / MCU add-remove / link change vs a saved baseline).
const diff = ref<TopologyDiff | null>(null)
/** Errors from override/snapshot ACTIONS — shown as a banner; never hides the loaded map. */
const actionError = ref<string | null>(null)
const snapshotBusy = ref(false)
const copied = ref(false)

const selectedMcu = computed(() => {
  if (!topology.value || !selected.value || selected.value === 'host') return null
  return topology.value.mcus.find((m) => 'mcu:' + m.name === selected.value) ?? null
})
const isHost = computed(() => selected.value === 'host')
const selectedFw = computed(() =>
  selectedMcu.value ? fwMcus.value[selectedMcu.value.name] : undefined,
)

/** Deep-link a related entity into the Hardware Browser (topology unmounts, the browser mounts and
 *  opens the target — its focus watch is `immediate`, so a focus set before mount still applies). */
function openInBrowser(ref: RelatedRef): void {
  const target = targetFor(ref)
  if (!target) return
  focusEntity(target)
  go('hardware-browser')
}

function defaultSelection(topo: Topology): string | null {
  const primary = topo.mcus.find((m) => m.name === 'mcu') ?? topo.mcus[0]
  return primary ? 'mcu:' + primary.name : topo.host ? 'host' : null
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchTopology()
    topology.value = data
    error.value = data.reachable === false ? t('boardTopology.states.unreachable') : null
    if (
      data.mcus.length &&
      (!selected.value || !data.mcus.some((m) => 'mcu:' + m.name === selected.value))
    ) {
      selected.value = defaultSelection(data)
    }
    fetchFirmwareStatus()
      .then((fw) => {
        fwMcus.value = Object.fromEntries((fw.mcus ?? []).map((m) => [m.name, m]))
      })
      .catch(() => {
        fwMcus.value = {}
      })
    fetchDiff()
      .then((d) => (diff.value = d))
      .catch(() => (diff.value = null))
  } catch (e) {
    error.value = describeError(e)
    topology.value = null
  } finally {
    loading.value = false
  }
}

async function setOverride(mcuName: string, boardId: string): Promise<void> {
  overrideBusy.value = true
  try {
    topology.value = await setBoardOverride(mcuName, boardId)
  } catch (e) {
    actionError.value = describeError(e)
  } finally {
    overrideBusy.value = false
  }
}
async function clearOverride(mcuName: string): Promise<void> {
  overrideBusy.value = true
  try {
    topology.value = await clearBoardOverride(mcuName)
  } catch (e) {
    actionError.value = describeError(e)
  } finally {
    overrideBusy.value = false
  }
}

async function takeSnapshot(): Promise<void> {
  snapshotBusy.value = true
  try {
    diff.value = await saveSnapshot()
  } catch (e) {
    actionError.value = describeError(e)
  } finally {
    snapshotBusy.value = false
  }
}

function changeMsg(c: TopologyChange): string {
  return t('boardTopology.snapshot.change.' + c.kind, {
    mcu: c.mcu,
    before: c.before ?? '—',
    after: c.after ?? '—',
  })
}

/** A plain-text machine inventory for pasting into a forum / issue post. */
async function copySummary(): Promise<void> {
  const topo = topology.value
  if (!topo) return
  const lines: string[] = [t('boardTopology.snapshot.summaryTitle')]
  if (topo.host) {
    const id = topo.host.host_id ? ` (${topo.host.host_id})` : ''
    lines.push(t('boardTopology.snapshot.summaryHost', { name: `${topo.host.name}${id}` }))
    if (topo.host.integrated_into_board_id)
      lines.push(
        `  ${t('boardTopology.snapshot.summaryIntegrated', { board: topo.host.integrated_into_board_id })}`,
      )
  }
  for (const m of topo.mcus) {
    const parts = [
      t('boardTopology.snapshot.summaryMcu', { name: m.name }),
      m.mcu || m.mcu_id || '?',
      t('boardTopology.snapshot.summaryBoard', { board: m.board_id || '?' }),
      `(${m.connection})`,
    ]
    if (m.components?.length)
      parts.push(t('boardTopology.snapshot.summaryComponents', { n: m.components.length }))
    lines.push(parts.join(' · '))
  }
  try {
    await navigator.clipboard?.writeText(lines.join('\n'))
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}

const LEGEND = [
  { tk: 'usb', cls: 'bg-brand-lime' },
  { tk: 'canbus', cls: 'bg-brand-cyan' },
  { tk: 'uart', cls: 'bg-brand-yellow' },
]

onMounted(() => void load())
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('boardTopology.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="boardTopology"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="boardTopology.help.steps"
          :button-label="t('boardTopology.help.guide')"
          :title="t('boardTopology.help.guideTitle')"
          :close-label="t('boardTopology.help.close')"
          :steps-title="t('boardTopology.help.howToRead')"
        />
        <HelpIllo illo="host" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- Controls: view toggle + refresh -->
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div
        class="inline-flex overflow-hidden rounded-brutal border-2 border-ink"
        role="group"
        :aria-label="t('boardTopology.graph.viewLabel')"
      >
        <button
          v-for="v in ['physical', 'logical'] as const"
          :key="v"
          type="button"
          class="px-2 py-1 text-xs font-bold"
          :class="view === v ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
          :aria-pressed="view === v"
          @click="view = v"
        >
          {{ t('boardTopology.graph.view.' + v) }}
        </button>
      </div>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" :disabled="loading" @click="load">
        <span aria-hidden="true">↻</span> {{ t('boardTopology.states.refresh') }}
      </button>
    </div>

    <!-- States -->
    <p v-if="loading && !topology" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p role="alert" class="font-mono text-xs">{{ error }}</p>
      <p v-if="topology?.detail" class="font-mono text-[11px] opacity-70">{{ topology.detail }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load">
        {{ t('boardTopology.states.retry') }}
      </button>
    </div>
    <p v-else-if="topology && !topology.mcus.length" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.empty') }}
    </p>

    <!-- Machine Map -->
    <template v-if="topology && !error && topology.mcus.length">
      <p class="text-[10px] opacity-60">
        {{ t('boardTopology.count', { n: topology.mcu_count }) }}
      </p>

      <!-- Legend -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px]">
        <span v-for="l in LEGEND" :key="l.tk" class="inline-flex items-center gap-1">
          <span
            class="inline-block h-2.5 w-3 rounded-sm border border-ink"
            :class="l.cls"
            aria-hidden="true"
          ></span>
          {{ t('boardTopology.conn.' + l.tk) }}
        </span>
        <span class="inline-flex items-center gap-1">
          <span
            class="inline-block h-2.5 w-3 rounded-sm border border-ink bg-brand-blue/55"
            aria-hidden="true"
          ></span>
          {{ t('boardTopology.graph.integrated') }}
        </span>
        <span class="opacity-70"
          >✓ {{ t('boardTopology.override.confirmed') }} · ◉
          {{ t('boardTopology.board.suggested') }}</span
        >
        <span class="opacity-70"
          >{{ t('boardTopology.graph.health.title') }}: <span class="text-brand-lime">✓</span>
          {{ t('boardTopology.graph.health.ok') }} · <span class="text-brand-red">✕</span>
          {{ t('boardTopology.graph.health.out') }}</span
        >
      </div>

      <div class="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <TopologyGraph
          :topology="topology"
          :view="view"
          :selected="selected"
          :health="fwMcus"
          @select="(id) => (selected = id)"
        />
        <NodeInspector
          :mcu="selectedMcu"
          :host="topology.host"
          :is-host="isHost"
          :busy="overrideBusy"
          :fw="selectedFw"
          @open-in-browser="openInBrowser"
          @set-override="setOverride"
          @clear-override="clearOverride"
        />
      </div>

      <!-- Action errors (override / snapshot) — a banner, not a map-hiding state -->
      <div
        v-if="actionError"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red/10 px-2 py-1"
      >
        <span class="min-w-0 flex-1 font-mono text-[11px]">{{ actionError }}</span>
        <button
          class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[10px]"
          @click="actionError = null"
        >
          ✕
        </button>
      </div>

      <!-- Hardware snapshot / diff + share -->
      <div class="space-y-1 border-t border-ink/15 pt-2">
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          <button
            type="button"
            class="nb-btn bg-surface px-2 py-0.5"
            :disabled="snapshotBusy"
            @click="takeSnapshot"
          >
            <span aria-hidden="true">📸</span> {{ t('boardTopology.snapshot.save') }}
          </button>
          <button type="button" class="nb-btn bg-surface px-2 py-0.5" @click="copySummary">
            {{ copied ? t('boardTopology.snapshot.copied') : t('boardTopology.snapshot.copy') }}
          </button>
          <span v-if="diff && !diff.has_baseline" class="opacity-60">{{
            t('boardTopology.snapshot.none')
          }}</span>
          <span
            v-else-if="diff && diff.has_baseline && diff.reachable === false"
            class="font-bold opacity-70"
          >
            ? {{ t('boardTopology.snapshot.noCompare') }}
          </span>
          <span
            v-else-if="diff && diff.has_baseline && !diff.changes.length"
            class="font-bold text-brand-lime"
          >
            ✓ {{ t('boardTopology.snapshot.unchanged') }}
          </span>
          <span v-else-if="diff && diff.changes.length" class="font-bold text-brand-red">
            ⚠ {{ t('boardTopology.snapshot.changed', { n: diff.changes.length }) }}
          </span>
        </div>
        <ul v-if="diff && diff.changes.length" class="space-y-0.5 text-[10px]">
          <li
            v-for="(c, i) in diff.changes"
            :key="i"
            class="rounded border-s-4 border-brand-red bg-brand-red/10 px-1 py-0.5"
          >
            {{ changeMsg(c) }}
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>
