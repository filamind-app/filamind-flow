<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { fetchFirmwareStatus } from '@/widgets/firmware-upgrade/api'
import { targetFor, useEntityFocus } from '@/widgets/hardware-browser/useEntityFocus'

import { clearBoardOverride, fetchTopology, setBoardOverride } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import NodeInspector from './NodeInspector.vue'
import TopologyGraph from './TopologyGraph.vue'
import type { RelatedRef, Topology } from './types'

const { t } = useI18n({ useScope: 'global' })
const { go } = useNav()
const { focusEntity } = useEntityFocus()

const topology = ref<Topology | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const fwSync = ref<Record<string, boolean | null>>({})

const view = ref<'logical' | 'physical'>('physical')
const selected = ref<string | null>(null)
const overrideBusy = ref(false)

const selectedMcu = computed(() => {
  if (!topology.value || !selected.value || selected.value === 'host') return null
  return topology.value.mcus.find((m) => 'mcu:' + m.name === selected.value) ?? null
})
const isHost = computed(() => selected.value === 'host')
const selectedFwSync = computed(() =>
  selectedMcu.value ? fwSync.value[selectedMcu.value.name] : null,
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
        fwSync.value = Object.fromEntries((fw.mcus ?? []).map((m) => [m.name, m.in_sync]))
      })
      .catch(() => {
        fwSync.value = {}
      })
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
    error.value = describeError(e)
  } finally {
    overrideBusy.value = false
  }
}
async function clearOverride(mcuName: string): Promise<void> {
  overrideBusy.value = true
  try {
    topology.value = await clearBoardOverride(mcuName)
  } catch (e) {
    error.value = describeError(e)
  } finally {
    overrideBusy.value = false
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
      <p class="font-mono text-xs">{{ error }}</p>
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
      </div>

      <div class="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <TopologyGraph
          :topology="topology"
          :view="view"
          :selected="selected"
          @select="(id) => (selected = id)"
        />
        <NodeInspector
          :mcu="selectedMcu"
          :host="topology.host"
          :is-host="isHost"
          :busy="overrideBusy"
          :fw-sync="selectedFwSync"
          @open-in-browser="openInBrowser"
          @set-override="setOverride"
          @clear-override="clearOverride"
        />
      </div>
    </template>
  </div>
</template>
