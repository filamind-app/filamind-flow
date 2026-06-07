<script setup lang="ts">
/** The board catalog view: browse the canonical boards[] entity (specs + aggregated
 *  ports[] + reference media links). This is where the enriched board data is seen. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchBoardDetail, fetchBoards } from './api'
import type { BoardDetail, BoardMedia, BoardSummary } from './types'

const { t } = useI18n({ useScope: 'global' })
const LIMIT = 24

const q = ref('')
const boards = ref<BoardSummary[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const openId = ref<string | null>(null)
const detailCache = ref<Record<string, BoardDetail>>({})
const detailLoading = ref<string | null>(null)

const hasNext = computed(() => offset.value + boards.value.length < total.value)
const hasPrev = computed(() => offset.value > 0)

async function load(reset = true): Promise<void> {
  if (reset) offset.value = 0
  loading.value = true
  try {
    const r = await fetchBoards({ q: q.value, limit: LIMIT, offset: offset.value })
    boards.value = r.boards
    total.value = r.total
    error.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * LIMIT)
  void load(false)
}

async function toggle(id: string): Promise<void> {
  if (openId.value === id) {
    openId.value = null
    return
  }
  openId.value = id
  if (!detailCache.value[id]) {
    detailLoading.value = id
    try {
      detailCache.value[id] = await fetchBoardDetail(id)
    } catch {
      openId.value = null
    } finally {
      detailLoading.value = null
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
function mediaLinks(media?: BoardMedia): { url: string; label: string }[] {
  if (!media) return []
  return LINK_FIELDS.filter((f) => media[f.key]).map((f) => ({
    url: media[f.key] as string,
    label: t(`boardTopology.board.links.${f.tk}`),
  }))
}

onMounted(() => void load(true))
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.boards.search')
        }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t('hardwareBrowser.boards.search')"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
          @keyup.enter="load(true)"
        />
      </label>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
        :disabled="loading"
        @click="load(true)"
      >
        {{ t('hardwareBrowser.search.button') }}
      </button>
    </div>

    <p v-if="loading && !boards.length" class="font-mono text-xs opacity-70">
      {{ t('hardwareBrowser.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-[11px]">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load(false)">
        {{ t('hardwareBrowser.states.retry') }}
      </button>
    </div>

    <template v-else>
      <p class="font-mono text-[11px] opacity-60">
        {{ t('hardwareBrowser.boards.total', { n: total }) }}
      </p>
      <p v-if="!boards.length" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.boards.none') }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="b in boards" :key="b.board_id" class="nb-card bg-surface p-2">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ b.display_name || b.model }}</div>
              <div class="font-mono text-[10px] opacity-60">
                <span v-if="b.manufacturer">{{ b.manufacturer }} · </span>{{ b.boardClass }} ·
                {{ t('boardTopology.board.ports', { n: b.portCount ?? 0 }) }}
              </div>
            </div>
            <button
              class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggle(b.board_id)"
            >
              {{
                openId === b.board_id
                  ? t('hardwareBrowser.boards.hide')
                  : t('hardwareBrowser.boards.view')
              }}
            </button>
          </div>

          <!-- ports summary chips -->
          <div v-if="b.portsSummary" class="mt-1 flex flex-wrap gap-1">
            <span
              v-for="(n, cat) in b.portsSummary"
              :key="cat"
              class="rounded bg-paper px-1 font-mono text-[9px]"
            >
              {{ cat }}×{{ n }}
            </span>
          </div>

          <!-- expanded detail -->
          <div v-if="openId === b.board_id" class="mt-2 space-y-2 border-t-2 border-ink pt-2">
            <p v-if="detailLoading === b.board_id" class="font-mono text-[11px] opacity-70">
              {{ t('boardTopology.board.loading') }}
            </p>
            <template v-else-if="detailCache[b.board_id]">
              <!-- specs -->
              <dl
                v-if="Object.keys(detailCache[b.board_id].specs || {}).length"
                class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]"
              >
                <template v-for="(val, key) in detailCache[b.board_id].specs" :key="key">
                  <dt class="opacity-60">{{ key }}</dt>
                  <dd class="min-w-0">{{ val }}</dd>
                </template>
              </dl>

              <!-- media links -->
              <div
                v-if="mediaLinks(detailCache[b.board_id].media).length"
                class="flex flex-wrap items-center gap-1"
              >
                <span class="text-[10px] opacity-60"
                  >{{ t('boardTopology.board.links.title') }}:</span
                >
                <a
                  v-for="lnk in mediaLinks(detailCache[b.board_id].media)"
                  :key="lnk.url"
                  :href="lnk.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="nb-btn bg-paper px-1 py-0 text-[9px]"
                >
                  {{ lnk.label }}
                </a>
              </div>

              <!-- ports table -->
              <div v-if="detailCache[b.board_id].ports?.length" class="overflow-x-auto">
                <table class="w-full border-collapse font-mono text-[9px]">
                  <thead>
                    <tr class="border-b-2 border-ink text-left">
                      <th class="pr-2">{{ t('hardwareBrowser.boards.connector') }}</th>
                      <th class="pr-2">{{ t('hardwareBrowser.boards.function') }}</th>
                      <th class="pr-2">{{ t('hardwareBrowser.boards.pins') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(p, i) in detailCache[b.board_id].ports"
                      :key="i"
                      class="border-b border-ink/20"
                    >
                      <td class="pr-2">{{ p.connectorStyle || p.label }}</td>
                      <td class="pr-2">{{ p.portFunction }}</td>
                      <td class="pr-2">{{ p.pins }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>
        </li>
      </ul>

      <div v-if="total > LIMIT" class="flex items-center justify-center gap-2">
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasPrev || loading"
          @click="page(-1)"
        >
          ‹ {{ t('hardwareBrowser.results.prev') }}
        </button>
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasNext || loading"
          @click="page(1)"
        >
          {{ t('hardwareBrowser.results.next') }} ›
        </button>
      </div>
    </template>
  </div>
</template>
