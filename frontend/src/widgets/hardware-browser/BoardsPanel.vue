<script setup lang="ts">
/** The board catalog view: browse the canonical boards[] entity (specs + aggregated
 *  ports[] + reference media links). Thin wrapper over the shared EntityCatalog. */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'

import { fetchBoardDetail, fetchBoards } from './api'
import EntityCatalog from './EntityCatalog.vue'
import { onPrinter } from './onPrinter'
import RelatedChips from './RelatedChips.vue'
import type { BoardDetail, BoardMedia, BoardSummary } from './types'
import type { FocusTarget } from './useEntityFocus'
import { useFacets } from './useFacets'

const { t } = useI18n({ useScope: 'global' })

const boardClass = ref<string | null>(null)
const manufacturer = ref('')
const reloadToken = ref(0)
const { facets } = useFacets()
const classOptions = computed(() =>
  (facets.value?.boardClass ?? []).map((v) => ({
    value: v,
    label: t(`hardwareBrowser.facets.boardClass.${v}`),
  })),
)
function onFacetChange(): void {
  reloadToken.value += 1
}

async function fetchPage(p: { q: string; offset: number; limit: number }) {
  const r = await fetchBoards({
    q: p.q,
    manufacturer: manufacturer.value,
    boardClass: boardClass.value ?? '',
    limit: p.limit,
    offset: p.offset,
  })
  return { items: r.boards, total: r.total }
}
const idOf = (b: BoardSummary): string => b.board_id
const focusMatch = (f: FocusTarget): boolean => f.tab === 'boards'

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
</script>

<template>
  <EntityCatalog
    :fetch-page="fetchPage"
    :fetch-detail="fetchBoardDetail"
    :id-of="idOf"
    :on-printer-ids="onPrinter.boards"
    :focus-match="focusMatch"
    :reload-token="reloadToken"
    search-key="hardwareBrowser.boards.search"
    total-key="hardwareBrowser.boards.total"
    none-key="hardwareBrowser.boards.none"
  >
    <template #facets>
      <div class="min-w-[8rem]">
        <ComboSelect
          v-model="boardClass"
          :options="classOptions"
          :placeholder="t('hardwareBrowser.facets.anyClass')"
          clearable
          @update:model-value="onFacetChange"
        />
      </div>
      <input
        v-model="manufacturer"
        type="text"
        :placeholder="t('hardwareBrowser.facets.manufacturer')"
        class="min-w-[8rem] rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
        @keyup.enter="onFacetChange"
      />
    </template>

    <template
      #summary="{ item, open, toggle }: { item: BoardSummary; open: boolean; toggle: () => void }"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate font-bold">{{ item.display_name || item.model }}</div>
          <div class="font-mono text-[10px] opacity-60">
            <span v-if="item.manufacturer">{{ item.manufacturer }} · </span>{{ item.boardClass }} ·
            {{ t('boardTopology.board.ports', { n: item.portCount ?? 0 }) }}
          </div>
        </div>
        <button class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]" @click="toggle">
          {{ open ? t('hardwareBrowser.boards.hide') : t('hardwareBrowser.boards.view') }}
        </button>
      </div>
      <div v-if="item.portsSummary" class="mt-1 flex flex-wrap gap-1">
        <span
          v-for="(n, cat) in item.portsSummary"
          :key="cat"
          class="rounded bg-paper px-1 font-mono text-[9px]"
        >
          {{ cat }}×{{ n }}
        </span>
      </div>
    </template>

    <template
      #detail="{
        detail,
        copied,
        copy,
      }: {
        detail: BoardDetail
        copied: boolean
        copy: (t: string) => void
      }"
    >
      <!-- specs -->
      <dl
        v-if="Object.keys(detail.specs || {}).length"
        class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]"
      >
        <template v-for="(val, key) in detail.specs" :key="key">
          <dt class="opacity-60">{{ key }}</dt>
          <dd class="min-w-0">{{ val }}</dd>
        </template>
      </dl>

      <!-- media links -->
      <div v-if="mediaLinks(detail.media).length" class="flex flex-wrap items-center gap-1">
        <span class="text-[10px] opacity-60">{{ t('boardTopology.board.links.title') }}:</span>
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

      <!-- ports table (with Klipper pins + usage hint = usable, not just viewable) -->
      <div v-if="detail.ports?.length" class="overflow-x-auto">
        <table class="w-full border-collapse font-mono text-[9px]">
          <thead>
            <tr class="border-b-2 border-ink text-left">
              <th class="pr-2">{{ t('hardwareBrowser.boards.connector') }}</th>
              <th class="pr-2">{{ t('hardwareBrowser.boards.function') }}</th>
              <th class="pr-2">{{ t('hardwareBrowser.boards.pins') }}</th>
              <th class="pr-2">{{ t('hardwareBrowser.boards.use') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, i) in detail.ports" :key="i" class="border-b border-ink/20 align-top">
              <td class="pr-2">{{ p.connectorStyle || p.label }}</td>
              <td class="pr-2">{{ p.portFunction }}</td>
              <td class="whitespace-nowrap pr-2">{{ p.pins }}</td>
              <td class="min-w-[12rem] pr-2 opacity-80">
                {{ p.hint }}
                <span v-if="p.configKey" class="opacity-60">[{{ p.configKey }}]</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- electronics that affect config / wiring decisions -->
      <div v-if="Object.keys(detail.electronics || {}).length">
        <div class="text-[10px] font-bold opacity-70">
          {{ t('hardwareBrowser.boards.electronics') }}
        </div>
        <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[10px]">
          <template v-for="(val, key) in detail.electronics" :key="key">
            <dt class="font-mono opacity-60">{{ key }}</dt>
            <dd class="min-w-0">{{ val }}</dd>
          </template>
        </dl>
      </div>

      <!-- config notes -->
      <div v-if="detail.configNotes?.length">
        <div class="text-[10px] font-bold opacity-70">{{ t('hardwareBrowser.boards.notes') }}</div>
        <ul class="list-disc pl-4 text-[10px]">
          <li v-for="(n, i) in detail.configNotes" :key="i">{{ n }}</li>
        </ul>
      </div>

      <!-- copy-ready config snippet -->
      <div v-if="detail.configSnippet">
        <div class="flex items-center justify-between">
          <span class="text-[10px] font-bold opacity-70">{{
            t('hardwareBrowser.boards.config')
          }}</span>
          <button
            class="nb-btn bg-brand-lime px-2 py-0 text-[9px]"
            @click="copy(detail.configSnippet || '')"
          >
            {{ copied ? t('hardwareBrowser.boards.copied') : t('hardwareBrowser.boards.copy') }}
          </button>
        </div>
        <pre
          class="overflow-x-auto rounded-brutal border-2 border-ink bg-paper p-2 text-[9px] leading-tight"
          >{{ detail.configSnippet }}</pre
        >
      </div>

      <!-- cross-entity links (manufacturer / MCUs / drivers) -->
      <RelatedChips :id="detail.board_id" type="boards" />
    </template>
  </EntityCatalog>
</template>
