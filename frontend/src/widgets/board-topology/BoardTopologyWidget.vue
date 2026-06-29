<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { fetchFirmwareStatus } from '@/widgets/firmware-upgrade/api'
import type { McuFirmware } from '@/widgets/firmware-upgrade/types'
import { targetFor, useEntityFocus } from '@/widgets/hardware-browser/useEntityFocus'

import {
  addManualAddition,
  clearBoardOverride,
  fetchDiff,
  fetchTopology,
  removeManualAddition,
  saveSnapshot,
  setBoardOverride,
} from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import ManualAdditionModal from './ManualAdditionModal.vue'
import NodeInspector from './NodeInspector.vue'
import { pendingNode } from './topologyFocus'
import TopologyGraph from './TopologyGraph.vue'
import type { ManualAddition, RelatedRef, Topology, TopologyChange, TopologyDiff } from './types'

const { t, te } = useI18n({ useScope: 'global' })
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
/** Errors from override/snapshot ACTIONS - shown as a banner; never hides the loaded map. */
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
/** The CAN adapter node (id `canbus:<iface>`) when its node is selected, else null. */
const selectedCanBus = computed(() => {
  const sel = selected.value
  if (!topology.value || !sel || !sel.startsWith('canbus:')) return null
  return (topology.value.can_buses ?? []).find((b) => 'canbus:' + b.interface === sel) ?? null
})

/** Deep-link a related entity into the Hardware Browser (topology unmounts, the browser mounts and
 *  opens the target - its focus watch is `immediate`, so a focus set before mount still applies). */
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

// -- Manual additions (user-added nodes the detection missed) ---------------------------
const manualOpen = ref(false)
const editingEntry = ref<ManualAddition | null>(null)

function openAddManual(): void {
  editingEntry.value = null
  manualOpen.value = true
}
function onEditManual(entry: ManualAddition): void {
  editingEntry.value = entry
  manualOpen.value = true
}
async function onManualSubmit(entry: ManualAddition): Promise<void> {
  overrideBusy.value = true
  try {
    topology.value = await addManualAddition(entry)
    manualOpen.value = false
  } catch (e) {
    actionError.value = describeError(e)
  } finally {
    overrideBusy.value = false
  }
}
async function onDeleteManual(id: string): Promise<void> {
  overrideBusy.value = true
  try {
    topology.value = await removeManualAddition(id)
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
    before: c.before ?? '-',
    after: c.after ?? '-',
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

/** A CAN bitrate as a short label: exact-MHz as "N Mbit", otherwise kbit. */
function fmtBitrate(n?: number | null): string {
  if (!n) return ''
  return n % 1_000_000 === 0 ? `${n / 1_000_000} Mbit` : `${Math.round(n / 1000)} kbit`
}

// -- CAN 120Ω termination advisory --------------------------------------------
/** Translate a termination type/default code, falling back to the raw value. */
function termLabel(key: string, raw: string): string {
  return te(key) ? t(key) : raw
}
function termType(type?: string | null): string {
  if (!type) return ''
  return termLabel('boardTopology.termination.type.' + type, type.replace(/_/g, ' '))
}
function termDefault(d?: string | null): string {
  if (!d) return ''
  return termLabel('boardTopology.termination.default.' + d, d)
}
function termFinding(f: { code: string; count?: number | null }): string {
  return t('boardTopology.termination.finding.' + f.code, { count: f.count ?? 0 })
}

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
          class="nb-seg"
          :class="view === v ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
          :aria-pressed="view === v"
          @click="view = v"
        >
          {{ t('boardTopology.graph.view.' + v) }}
        </button>
      </div>
      <div class="flex items-center gap-2">
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="openAddManual">
          <span aria-hidden="true">＋</span> {{ t('boardTopology.manual.add') }}
        </button>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" :disabled="loading" @click="load">
          <span aria-hidden="true">↻</span> {{ t('boardTopology.states.refresh') }}
        </button>
      </div>
    </div>

    <!-- States -->
    <p v-if="loading && !topology" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p role="alert" class="font-mono text-xs">{{ error }}</p>
      <p v-if="topology?.detail" class="font-mono text-[11px] opacity-70">{{ topology.detail }}</p>
      <div class="flex flex-wrap items-center gap-2">
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load">
          {{ t('boardTopology.states.retry') }}
        </button>
        <ReportErrorButton :error="error" />
      </div>
    </div>
    <p v-else-if="topology && !topology.mcus.length" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.empty') }}
    </p>

    <!-- Machine Map -->
    <template v-if="topology && !error && topology.mcus.length">
      <p class="text-xs opacity-60">
        {{ t('boardTopology.count', { n: topology.mcu_count }) }}
      </p>

      <!-- CAN bus(es) + bridging adapter: a USB-CAN dongle (U2C-class) isn't a Klipper MCU, so it
           has no node - this is the only place it shows. -->
      <div
        v-if="topology.can_buses && topology.can_buses.length"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs"
      >
        <span
          v-for="b in topology.can_buses"
          :key="b.interface"
          class="inline-flex items-center gap-1"
          dir="ltr"
        >
          <span class="opacity-60">{{ t('boardTopology.canbus.label') }}:</span>
          <span class="rounded-sm bg-paper px-1">{{ b.interface }}</span>
          <span v-if="b.bitrate" class="opacity-70">{{ fmtBitrate(b.bitrate) }}</span>
          <span v-if="b.driver" class="opacity-50">· {{ b.driver }}</span>
          <span v-if="b.board_id" class="opacity-70"
            >· {{ t('boardTopology.canbus.adapter') }}</span
          >
        </span>
      </div>

      <!-- CAN 120Ω termination advisory: where each board's terminator is + the exactly-two rule -->
      <div
        v-if="topology.can_termination && topology.can_termination.nodes.length"
        class="nb-card space-y-1.5 bg-surface p-2 text-xs"
      >
        <p class="font-bold">
          <span aria-hidden="true">⏛</span> {{ t('boardTopology.termination.title') }}
        </p>
        <p class="opacity-70">{{ t('boardTopology.termination.intro') }}</p>
        <ul class="space-y-0.5" dir="ltr">
          <li
            v-for="n in topology.can_termination.nodes"
            :key="n.role + n.name"
            class="flex flex-wrap items-baseline gap-x-1.5"
          >
            <span class="font-mono font-bold">{{ n.name }}</span>
            <span class="opacity-50">({{ t('boardTopology.termination.role.' + n.role) }})</span>
            <template v-if="n.termination">
              <span>· {{ termType(n.termination.type) }}</span>
              <span v-if="n.termination.location" class="opacity-70"
                >— {{ n.termination.location }}</span
              >
              <span v-if="termDefault(n.termination.default)" class="opacity-60"
                >· {{ termDefault(n.termination.default) }}</span
              >
            </template>
            <span v-else class="opacity-50">· {{ t('boardTopology.termination.unknownLoc') }}</span>
          </li>
        </ul>
        <ul class="space-y-0.5">
          <li
            v-for="(f, i) in topology.can_termination.findings"
            :key="i"
            class="rounded-sm px-1 py-0.5"
            :class="f.level === 'warning' ? 'bg-brand-yellow/20 font-bold' : 'opacity-70'"
          >
            {{ termFinding(f) }}
          </li>
        </ul>
      </div>

      <!-- Legend -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" dir="auto">
        <span v-for="l in LEGEND" :key="l.tk" class="inline-flex items-center gap-1">
          <span
            class="inline-block h-2.5 w-3 rounded-xs border border-ink"
            :class="l.cls"
            aria-hidden="true"
          ></span>
          {{ t('boardTopology.conn.' + l.tk) }}
        </span>
        <span class="inline-flex items-center gap-1">
          <span
            class="inline-block h-2.5 w-3 rounded-xs border border-ink bg-brand-blue/55"
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

      <div class="grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
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
          :can-bus="selectedCanBus"
          :busy="overrideBusy"
          :fw="selectedFw"
          @open-in-browser="openInBrowser"
          @set-override="setOverride"
          @clear-override="clearOverride"
          @edit-manual="onEditManual"
          @delete-manual="onDeleteManual"
        />
      </div>

      <!-- Action errors (override / snapshot) - a banner, not a map-hiding state -->
      <div
        v-if="actionError"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red/10 px-2 py-1"
      >
        <span class="min-w-0 flex-1 font-mono text-[11px]">{{ actionError }}</span>
        <button class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-xs" @click="actionError = null">
          ✕
        </button>
      </div>

      <!-- Hardware snapshot / diff + share -->
      <div class="space-y-1 border-t border-ink/15 pt-2">
        <div class="flex flex-wrap items-center gap-2 text-xs">
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
        <ul v-if="diff && diff.changes.length" class="space-y-0.5 text-xs">
          <li
            v-for="(c, i) in diff.changes"
            :key="i"
            class="rounded-sm border-s-4 border-brand-red bg-brand-red/10 px-1 py-0.5"
          >
            {{ changeMsg(c) }}
          </li>
        </ul>
      </div>
    </template>

    <ManualAdditionModal
      :open="manualOpen"
      :entry="editingEntry"
      :busy="overrideBusy"
      @close="manualOpen = false"
      @submit="onManualSubmit"
    />
  </div>
</template>
