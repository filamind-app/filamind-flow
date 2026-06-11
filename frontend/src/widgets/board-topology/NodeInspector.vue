<script setup lang="ts">
/** The inspector panel for the selected node in the Machine Map. For an MCU it shows the rich
 *  catalog board record (specs / ports / electronics caveats / config notes / copyable snippet /
 *  cross-entity deep-links) plus the confirm / change / clear board-override write path. For the
 *  host it shows the SBC and, when integrated, the mainboard it sits on. Self-contained board fetch;
 *  override + deep-link actions are emitted to the parent (which owns the topology state). */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { McuFirmware } from '@/widgets/firmware-upgrade/types'
import HardwarePicker from '@/widgets/hardware-browser/HardwarePicker.vue'

import { fetchBoardDetail } from './api'
import type { BoardDetail, BoardMedia, RelatedRef, TopologyHost, TopologyMcu } from './types'

const props = defineProps<{
  mcu: TopologyMcu | null
  host: TopologyHost | null
  isHost: boolean
  busy: boolean
  fw: McuFirmware | undefined
}>()
const emit = defineEmits<{
  openInBrowser: [ref: RelatedRef]
  setOverride: [mcuName: string, boardId: string]
  clearOverride: [mcuName: string]
}>()

const { t } = useI18n({ useScope: 'global' })

const detail = ref<BoardDetail | null>(null)
const loadingBoard = ref(false)
const pickerOpen = ref(false)
const copied = ref(false)

watch(
  () => [props.isHost, props.mcu?.board_id] as const,
  async ([isHost, boardId]) => {
    detail.value = null
    pickerOpen.value = false
    if (isHost || !boardId) return
    loadingBoard.value = true
    try {
      detail.value = await fetchBoardDetail(boardId)
    } catch {
      detail.value = null
    } finally {
      loadingBoard.value = false
    }
  },
  { immediate: true },
)

const LINK_FIELDS: { key: keyof BoardMedia; tk: string }[] = [
  { key: 'pinoutUrl', tk: 'pinout' },
  { key: 'schematicUrl', tk: 'schematic' },
  { key: 'imageUrl', tk: 'image' },
  { key: 'productUrl', tk: 'product' },
  { key: 'repoUrl', tk: 'repo' },
  { key: 'wikiUrl', tk: 'wiki' },
  { key: 'datasheetUrl', tk: 'datasheet' },
]
function mediaLinks(media?: BoardMedia): { url: string; label: string }[] {
  if (!media) return []
  return LINK_FIELDS.filter((f) => media[f.key]).map((f) => ({
    url: media[f.key] as string,
    label: t(`boardTopology.board.links.${f.tk}`),
  }))
}

const REL_ORDER = [
  'manufacturer',
  'mcus',
  'onboardDrivers',
  'supportedDrivers',
  'motors',
  'hosts',
  'boards',
  'catalog',
]
function relatedGroups(d?: BoardDetail | null): { key: string; refs: RelatedRef[] }[] {
  const rel = d?.related
  if (!rel) return []
  const keys = [...REL_ORDER, ...Object.keys(rel).filter((k) => !REL_ORDER.includes(k))]
  return keys.filter((k) => (rel[k]?.length ?? 0) > 0).map((k) => ({ key: k, refs: rel[k] }))
}

const KIND_ORDER = ['motor', 'driver', 'heater', 'fan', 'sensor']
function componentCounts(m: TopologyMcu): { kind: string; n: number }[] {
  const comps = m.components ?? []
  return KIND_ORDER.map((k) => ({ kind: k, n: comps.filter((c) => c.kind === k).length })).filter(
    (x) => x.n > 0,
  )
}

async function copySnippet(text: string): Promise<void> {
  if (!text) return
  try {
    await navigator.clipboard?.writeText(text)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}

function onPick(id: string | null): void {
  if (id && props.mcu) emit('setOverride', props.mcu.name, id)
  pickerOpen.value = false
}
</script>

<template>
  <div class="nb-card space-y-2 bg-surface p-2 text-[11px]">
    <!-- Host inspector -->
    <template v-if="isHost && host">
      <div class="font-display text-sm font-bold">
        <span aria-hidden="true">🖥 </span
        >{{ host.name && host.name !== 'host' ? host.name : t('boardTopology.host.label') }}
      </div>
      <div class="opacity-70">{{ t('boardTopology.host.role') }}</div>
      <button
        v-if="host.host_id"
        type="button"
        class="nb-btn bg-paper px-1.5 py-0.5 hover:bg-brand-cyan"
        @click="emit('openInBrowser', { type: 'host', id: host.host_id, name: host.name })"
      >
        {{ t('hardwareBrowser.related.jump', { name: host.name }) }}
      </button>
      <p v-if="host.integrated_into_board_id" class="rounded bg-brand-blue/20 p-1">
        <span aria-hidden="true">🔗 </span
        >{{ t('boardTopology.graph.integratedNote', { board: host.integrated_into_board_id }) }}
      </p>
    </template>

    <!-- MCU inspector -->
    <template v-else-if="mcu">
      <div class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate font-display text-sm font-bold">{{ mcu.name }}</span>
        <span
          v-if="fw?.in_sync === true || fw?.in_sync === false"
          class="shrink-0 rounded px-1 text-[10px] font-bold"
          :class="fw.in_sync ? 'bg-brand-lime text-ink' : 'bg-brand-red text-surface'"
        >
          {{
            fw.in_sync
              ? '✓ ' + t('boardTopology.sync.synced')
              : '⚠ ' + t('boardTopology.sync.outOfSync')
          }}
        </span>
      </div>

      <!-- live link vitals (freq / retransmits / load) from the firmware status -->
      <div
        v-if="fw && (fw.freq != null || fw.retransmits != null || fw.awake != null)"
        class="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[10px] opacity-75"
      >
        <span v-if="fw.freq != null">{{
          t('boardTopology.graph.vitals.freq', { mhz: (fw.freq / 1e6).toFixed(2) })
        }}</span>
        <span v-if="fw.retransmits != null">{{
          t('boardTopology.graph.vitals.retx', { n: fw.retransmits })
        }}</span>
        <span v-if="fw.awake != null">{{
          t('boardTopology.graph.vitals.load', { pct: Math.round(fw.awake * 100) })
        }}</span>
      </div>

      <div class="font-mono">
        <span class="opacity-60">{{ t('boardTopology.mcu.chip') }}:</span>
        <button
          v-if="mcu.mcu_id"
          type="button"
          class="nb-btn rounded bg-paper px-1 hover:bg-brand-cyan"
          @click="
            emit('openInBrowser', { type: 'mcu', id: mcu.mcu_id, name: mcu.mcu || mcu.mcu_id })
          "
        >
          {{ mcu.mcu || mcu.mcu_id }}
        </button>
        <template v-else>{{ mcu.mcu || t('boardTopology.mcu.unknown') }}</template>
        <span v-if="mcu.mcu_family" class="opacity-50">· {{ mcu.mcu_family }}</span>
      </div>

      <div
        v-if="mcu.identifier"
        class="truncate font-mono text-[10px] opacity-50"
        :title="mcu.identifier"
      >
        {{ mcu.identifier }}
      </div>

      <!-- components -->
      <div
        v-if="componentCounts(mcu).length"
        class="flex flex-wrap items-center gap-1 font-mono text-[10px]"
      >
        <span class="opacity-60">{{ t('boardTopology.components.title') }}:</span>
        <span v-for="c in componentCounts(mcu)" :key="c.kind" class="rounded bg-paper px-1">
          {{ t('boardTopology.components.' + c.kind) }} ×{{ c.n }}
        </span>
      </div>

      <!-- board detail -->
      <div v-if="loadingBoard" class="font-mono opacity-70">
        {{ t('boardTopology.board.loading') }}
      </div>
      <div v-else-if="detail" class="space-y-1 border-t border-ink/15 pt-1">
        <div class="font-display text-[12px] font-bold">
          {{ detail.display_name || detail.model }}
        </div>
        <div
          v-if="detail.manufacturer || detail.boardClass"
          class="flex flex-wrap items-center gap-1 font-mono opacity-70"
        >
          <span v-if="detail.manufacturer">{{ detail.manufacturer }}</span>
          <span v-if="detail.boardClass" class="rounded bg-paper px-1">{{
            detail.boardClass
          }}</span>
        </div>
        <div v-if="detail.ports?.length" class="font-mono opacity-70">
          {{ t('boardTopology.board.portsTitle') }}:
          {{ t('boardTopology.board.ports', { n: detail.ports.length }) }}
          <span
            v-for="(n, cat) in detail.portsSummary"
            :key="cat"
            class="ml-1 inline-block rounded bg-paper px-1"
          >
            {{ cat }}×{{ n }}
          </span>
        </div>
        <dl
          v-if="Object.keys(detail.specs || {}).length"
          class="grid grid-cols-[auto_1fr] gap-x-2 font-mono"
        >
          <template v-for="(val, key) in detail.specs" :key="key">
            <dt class="opacity-60">{{ key }}</dt>
            <dd class="min-w-0 truncate">{{ val }}</dd>
          </template>
        </dl>
        <div
          v-if="mediaLinks(detail.media).length"
          class="flex flex-wrap items-center gap-1 pt-0.5"
        >
          <span class="opacity-60">{{ t('boardTopology.board.links.title') }}:</span>
          <a
            v-for="lnk in mediaLinks(detail.media)"
            :key="lnk.url"
            :href="lnk.url"
            target="_blank"
            rel="noopener noreferrer"
            class="nb-btn bg-paper px-1 py-0 text-[9px]"
          >
            {{ lnk.label }}
          </a>
        </div>
        <div v-if="relatedGroups(detail).length" class="space-y-0.5 border-t border-ink/20 pt-1">
          <span class="opacity-60">{{ t('hardwareBrowser.related.title') }}:</span>
          <div
            v-for="g in relatedGroups(detail)"
            :key="g.key"
            class="flex flex-wrap items-center gap-1"
          >
            <span class="opacity-50">{{ t('hardwareBrowser.related.rel.' + g.key) }}:</span>
            <button
              v-for="r in g.refs"
              :key="r.type + r.id"
              type="button"
              class="nb-btn rounded bg-paper px-1 font-mono hover:bg-brand-cyan"
              @click="emit('openInBrowser', r)"
            >
              {{ r.name || r.id }}
            </button>
          </div>
        </div>
        <div
          v-if="Object.keys(detail.electronics || {}).length"
          class="space-y-0.5 border-t border-ink/20 pt-1"
        >
          <span class="opacity-60">{{ t('hardwareBrowser.boards.electronics') }}:</span>
          <dl class="grid grid-cols-[auto_1fr] gap-x-2">
            <template v-for="(v, k) in detail.electronics" :key="k">
              <dt class="opacity-60">{{ k }}</dt>
              <dd class="min-w-0">{{ v }}</dd>
            </template>
          </dl>
        </div>
        <div v-if="detail.configNotes?.length" class="space-y-0.5">
          <span class="opacity-60">{{ t('hardwareBrowser.boards.notes') }}:</span>
          <ul class="list-disc ps-4">
            <li v-for="(n, ni) in detail.configNotes" :key="ni">{{ n }}</li>
          </ul>
        </div>
        <div v-if="detail.configSnippet" class="space-y-0.5">
          <div class="flex items-center gap-1">
            <span class="opacity-60">{{ t('hardwareBrowser.boards.config') }}:</span>
            <button
              type="button"
              class="nb-btn bg-paper px-1 py-0 text-[9px]"
              @click="copySnippet(detail.configSnippet || '')"
            >
              {{ copied ? t('hardwareBrowser.boards.copied') : t('hardwareBrowser.boards.copy') }}
            </button>
          </div>
          <pre
            class="overflow-x-auto rounded-brutal border border-ink/30 bg-paper p-1 text-[9px] leading-tight"
            >{{ detail.configSnippet }}</pre
          >
        </div>
      </div>
      <p v-else-if="!mcu.board_id" class="opacity-60">{{ t('boardTopology.board.noMatch') }}</p>

      <!-- confirm / override (the write path) -->
      <div class="flex flex-wrap items-center gap-1 border-t border-ink/15 pt-1 text-[10px]">
        <span
          v-if="mcu.board_match === 'confirmed'"
          class="rounded bg-brand-lime px-1 font-bold text-ink"
        >
          ✓ {{ t('boardTopology.override.confirmed') }}
        </span>
        <button
          v-if="mcu.board_id && mcu.board_match !== 'confirmed'"
          type="button"
          class="nb-btn bg-paper px-1 py-0 disabled:opacity-50"
          :disabled="busy"
          @click="emit('setOverride', mcu.name, mcu.board_id)"
        >
          {{ t('boardTopology.override.confirm') }}
        </button>
        <button
          type="button"
          class="nb-btn bg-paper px-1 py-0 disabled:opacity-50"
          :disabled="busy"
          @click="pickerOpen = !pickerOpen"
        >
          {{ mcu.board_id ? t('boardTopology.override.change') : t('boardTopology.override.set') }}
        </button>
        <button
          v-if="mcu.board_match === 'confirmed'"
          type="button"
          class="nb-btn bg-paper px-1 py-0 disabled:opacity-50"
          :disabled="busy"
          @click="emit('clearOverride', mcu.name)"
        >
          {{ t('boardTopology.override.clear') }}
        </button>
      </div>
      <div v-if="pickerOpen">
        <HardwarePicker
          type="boards"
          :model-value="mcu.board_id ?? null"
          :placeholder="t('boardTopology.override.pickPlaceholder')"
          :disabled="busy"
          @update:model-value="onPick"
        />
        <p class="pt-0.5 text-[10px] opacity-60">{{ t('boardTopology.override.hint') }}</p>
      </div>
    </template>

    <!-- nothing selected -->
    <p v-else class="py-2 text-center opacity-60">{{ t('boardTopology.graph.selectPrompt') }}</p>
  </div>
</template>
