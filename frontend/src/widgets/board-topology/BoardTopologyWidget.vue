<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import { targetFor, useEntityFocus } from '@/widgets/hardware-browser/useEntityFocus'

import { fetchBoardDetail, fetchTopology } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { BoardDetail, BoardMedia, RelatedRef, Topology } from './types'

const { t } = useI18n({ useScope: 'global' })
const { go } = useNav()
const { focusEntity } = useEntityFocus()

/** Deep-link a related entity into the Hardware Browser: set the shared focus then switch view.
 *  Topology unmounts and the Hardware Browser mounts + opens the target (its focus watch is
 *  `immediate`, so a focus set before it mounts still applies). */
function openInBrowser(ref: RelatedRef): void {
  const target = targetFor(ref)
  if (!target) return
  focusEntity(target)
  go('hardware-browser')
}

const topology = ref<Topology | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

// Lazy-loaded board catalog details, keyed by board_id, for the suggested matches.
const openBoard = ref<string | null>(null)
const boardCache = ref<Record<string, BoardDetail>>({})
const boardLoading = ref<string | null>(null)

async function toggleBoard(boardId: string): Promise<void> {
  if (openBoard.value === boardId) {
    openBoard.value = null
    return
  }
  openBoard.value = boardId
  if (!boardCache.value[boardId]) {
    boardLoading.value = boardId
    try {
      boardCache.value[boardId] = await fetchBoardDetail(boardId)
    } catch {
      openBoard.value = null
    } finally {
      boardLoading.value = null
    }
  }
}

const LINK_FIELDS: { key: keyof BoardMedia; tk: string }[] = [
  { key: 'pinoutUrl', tk: 'pinout' },
  { key: 'schematicUrl', tk: 'schematic' },
  { key: 'imageUrl', tk: 'image' },
  { key: 'productUrl', tk: 'product' },
  { key: 'repoUrl', tk: 'repo' },
  { key: 'wikiUrl', tk: 'wiki' },
  { key: 'datasheetUrl', tk: 'datasheet' },
]

/** Build the list of available reference links for a board (link-only). */
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

/** A board's non-empty cross-entity link groups (from `?expand=related`), in a stable order, for
 *  display. Navigation (clicking through to the Hardware Browser) is wired in a later phase. */
function relatedGroups(detail?: BoardDetail): { key: string; refs: RelatedRef[] }[] {
  const rel = detail?.related
  if (!rel) return []
  const keys = [...REL_ORDER, ...Object.keys(rel).filter((k) => !REL_ORDER.includes(k))]
  return keys.filter((k) => (rel[k]?.length ?? 0) > 0).map((k) => ({ key: k, refs: rel[k] }))
}

function connLabel(conn: string): string {
  switch (conn) {
    case 'canbus':
      return t('boardTopology.conn.canbus')
    case 'usb':
      return t('boardTopology.conn.usb')
    case 'uart':
      return t('boardTopology.conn.uart')
    default:
      return t('boardTopology.conn.unknown')
  }
}

function connClass(conn: string): string {
  switch (conn) {
    case 'canbus':
      return 'bg-brand-cyan text-ink'
    case 'usb':
      return 'bg-brand-lime text-ink'
    case 'uart':
      return 'bg-brand-yellow text-ink'
    default:
      return 'bg-paper text-ink'
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchTopology()
    topology.value = data
    error.value = data.reachable === false ? t('boardTopology.states.unreachable') : null
  } catch (e) {
    error.value = describeError(e)
    topology.value = null
  } finally {
    loading.value = false
  }
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

    <div class="flex justify-end">
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

    <!-- Topology -->
    <template v-if="topology && !error && topology.mcus.length">
      <!-- Host -->
      <div class="flex flex-col items-center gap-1">
        <div class="nb-card bg-brand-yellow px-3 py-2 text-center">
          <div class="font-display font-bold">
            <span aria-hidden="true">🖥</span> {{ t('boardTopology.host.label') }}
          </div>
          <div class="text-[10px] opacity-70">{{ t('boardTopology.host.role') }}</div>
        </div>
        <div class="h-4 w-0.5 bg-ink" aria-hidden="true"></div>
        <div class="text-[10px] opacity-60">
          {{ t('boardTopology.count', { n: topology.mcu_count }) }}
        </div>
      </div>

      <!-- MCU cards -->
      <ul class="grid gap-2 sm:grid-cols-2">
        <li v-for="(m, i) in topology.mcus" :key="i" class="nb-card space-y-1 bg-surface p-2">
          <div class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate font-mono text-xs font-bold">{{ m.name }}</span>
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
              :class="connClass(m.connection)"
            >
              {{ connLabel(m.connection) }}
            </span>
          </div>
          <div class="font-mono text-[11px]">
            <span class="opacity-60">{{ t('boardTopology.mcu.chip') }}:</span>
            {{ m.mcu || t('boardTopology.mcu.unknown') }}
          </div>
          <div v-if="m.board" class="font-mono text-[11px]">
            <span class="opacity-60">{{ t('boardTopology.mcu.board') }}:</span> {{ m.board }}
            <span v-if="m.confidence > 0" class="opacity-50">
              ({{ t('boardTopology.mcu.confidence', { pct: Math.round(m.confidence * 100) }) }})
            </span>
          </div>
          <div
            v-if="m.identifier"
            class="truncate font-mono text-[10px] opacity-50"
            :title="m.identifier"
          >
            {{ m.identifier }}
          </div>

          <!-- Catalog board link (suggested match) -->
          <template v-if="m.board_id">
            <button
              class="nb-btn w-full bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggleBoard(m.board_id)"
            >
              {{
                openBoard === m.board_id
                  ? t('boardTopology.mcu.hideBoard')
                  : t('boardTopology.mcu.viewBoard')
              }}
              <span class="opacity-70"
                >· {{ t('boardTopology.board.suggested')
                }}<template v-if="m.board_match_confidence">
                  {{ Math.round(m.board_match_confidence * 100) }}%</template
                ></span
              >
            </button>

            <div v-if="openBoard === m.board_id" class="nb-card space-y-1 bg-paper p-2 text-[10px]">
              <p v-if="boardLoading === m.board_id" class="font-mono opacity-70">
                {{ t('boardTopology.board.loading') }}
              </p>
              <template v-else-if="boardCache[m.board_id]">
                <div class="font-display text-[11px] font-bold">
                  {{ boardCache[m.board_id].display_name || boardCache[m.board_id].model }}
                </div>
                <div
                  v-if="boardCache[m.board_id].manufacturer || boardCache[m.board_id].boardClass"
                  class="flex flex-wrap items-center gap-1 font-mono opacity-70"
                >
                  <span v-if="boardCache[m.board_id].manufacturer">{{
                    boardCache[m.board_id].manufacturer
                  }}</span>
                  <span v-if="boardCache[m.board_id].boardClass" class="rounded bg-surface px-1">{{
                    boardCache[m.board_id].boardClass
                  }}</span>
                </div>
                <div v-if="boardCache[m.board_id].ports?.length" class="font-mono opacity-70">
                  {{ t('boardTopology.board.portsTitle') }}:
                  {{ t('boardTopology.board.ports', { n: boardCache[m.board_id].ports!.length }) }}
                  <span
                    v-for="(n, cat) in boardCache[m.board_id].portsSummary"
                    :key="cat"
                    class="ml-1 inline-block rounded bg-surface px-1"
                  >
                    {{ cat }}×{{ n }}
                  </span>
                </div>
                <dl
                  v-if="Object.keys(boardCache[m.board_id].specs || {}).length"
                  class="grid grid-cols-[auto_1fr] gap-x-2 font-mono"
                >
                  <template v-for="(val, key) in boardCache[m.board_id].specs" :key="key">
                    <dt class="opacity-60">{{ key }}</dt>
                    <dd class="min-w-0 truncate">{{ val }}</dd>
                  </template>
                </dl>
                <div
                  v-if="mediaLinks(boardCache[m.board_id].media).length"
                  class="flex flex-wrap items-center gap-1 pt-0.5"
                >
                  <span class="opacity-60">{{ t('boardTopology.board.links.title') }}:</span>
                  <a
                    v-for="lnk in mediaLinks(boardCache[m.board_id].media)"
                    :key="lnk.url"
                    :href="lnk.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="nb-btn bg-surface px-1 py-0 text-[9px]"
                  >
                    {{ lnk.label }}
                  </a>
                </div>
                <!-- Linked hardware from the DB graph (manufacturer / MCU / drivers …) -->
                <div
                  v-if="relatedGroups(boardCache[m.board_id]).length"
                  class="space-y-0.5 border-t border-ink/20 pt-1"
                >
                  <span class="opacity-60">{{ t('hardwareBrowser.related.title') }}:</span>
                  <div
                    v-for="g in relatedGroups(boardCache[m.board_id])"
                    :key="g.key"
                    class="flex flex-wrap items-center gap-1"
                  >
                    <span class="opacity-50">{{ t('hardwareBrowser.related.rel.' + g.key) }}:</span>
                    <button
                      v-for="r in g.refs"
                      :key="r.type + r.id"
                      type="button"
                      class="nb-btn rounded bg-surface px-1 font-mono hover:bg-brand-cyan"
                      :title="t('hardwareBrowser.related.jump', { name: r.name || r.id })"
                      @click="openInBrowser(r)"
                    >
                      {{ r.name || r.id }}
                    </button>
                  </div>
                </div>
                <p
                  v-if="
                    !boardCache[m.board_id].ports?.length &&
                    !Object.keys(boardCache[m.board_id].specs || {}).length &&
                    !mediaLinks(boardCache[m.board_id].media).length &&
                    !relatedGroups(boardCache[m.board_id]).length
                  "
                  class="opacity-60"
                >
                  {{ t('boardTopology.board.none') }}
                </p>
              </template>
            </div>
          </template>
        </li>
      </ul>
    </template>
  </div>
</template>
