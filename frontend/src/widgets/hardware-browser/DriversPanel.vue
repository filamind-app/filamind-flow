<script setup lang="ts">
/** The driver catalog view: specs + Klipper support + a copyable [tmcXXXX] config snippet.
 *  Thin wrapper over the shared EntityCatalog (adds a Klipper-only facet). */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchDriverDetail, fetchDrivers } from './api'
import EntityCatalog from './EntityCatalog.vue'
import RelatedChips from './RelatedChips.vue'
import type { DriverDetail, DriverSummary } from './types'
import type { FocusTarget } from './useEntityFocus'

const { t } = useI18n({ useScope: 'global' })

const klipperOnly = ref(false)
const manufacturer = ref('')
const reloadToken = ref(0)

async function fetchPage(p: { q: string; offset: number; limit: number }) {
  const r = await fetchDrivers({
    q: p.q,
    manufacturer: manufacturer.value,
    klipperOnly: klipperOnly.value,
    limit: p.limit,
    offset: p.offset,
  })
  return { items: r.drivers, total: r.total }
}
const idOf = (d: DriverSummary): string => d.driver_id
const focusMatch = (f: FocusTarget): boolean => f.tab === 'drivers'

function onFacetChange(): void {
  reloadToken.value += 1
}

/** Cleared before a cross-link deep-link so a standalone (non-Klipper) target isn't filtered out. */
function resetFacets(): void {
  klipperOnly.value = false
}
</script>

<template>
  <EntityCatalog
    :fetch-page="fetchPage"
    :fetch-detail="fetchDriverDetail"
    :id-of="idOf"
    :focus-match="focusMatch"
    :before-focus="resetFacets"
    :reload-token="reloadToken"
    search-key="hardwareBrowser.drivers.search"
    total-key="hardwareBrowser.drivers.total"
    none-key="hardwareBrowser.drivers.none"
  >
    <template #facets>
      <label class="flex items-center gap-1 text-[11px]">
        <input
          v-model="klipperOnly"
          type="checkbox"
          class="accent-brand-cyan"
          @change="onFacetChange"
        />
        {{ t('hardwareBrowser.drivers.klipperOnly') }}
      </label>
      <input
        v-model="manufacturer"
        type="text"
        :placeholder="t('hardwareBrowser.facets.manufacturer')"
        class="min-w-[8rem] rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
        @keyup.enter="onFacetChange"
      />
    </template>

    <template
      #summary="{ item, open, toggle }: { item: DriverSummary; open: boolean; toggle: () => void }"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate font-bold">{{ item.name }}</div>
          <div class="font-mono text-[10px] opacity-60">
            <span v-if="item.manufacturer">{{ item.manufacturer }} · </span>{{ item.interface }}
          </div>
        </div>
        <button class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]" @click="toggle">
          {{ open ? t('hardwareBrowser.boards.hide') : t('hardwareBrowser.boards.view') }}
        </button>
      </div>
      <div class="mt-1 flex flex-wrap gap-1">
        <span
          class="rounded px-1 font-mono text-[9px]"
          :class="item.klipperSupported ? 'bg-brand-lime' : 'bg-paper opacity-70'"
        >
          {{
            item.klipperSupported
              ? `[${item.klipperSection}]`
              : t('hardwareBrowser.drivers.standalone')
          }}
        </span>
        <span v-if="item.sensorless" class="rounded bg-paper px-1 font-mono text-[9px]">
          {{ t('hardwareBrowser.drivers.sensorless') }}
        </span>
      </div>
    </template>

    <template
      #detail="{
        detail,
        copied,
        copy,
      }: {
        detail: DriverDetail
        copied: boolean
        copy: (t: string) => void
      }"
    >
      <dl
        v-if="Object.keys(detail.specs || {}).length"
        class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]"
      >
        <template v-for="(val, key) in detail.specs" :key="key">
          <dt class="opacity-60">{{ key }}</dt>
          <dd class="min-w-0">{{ val }}</dd>
        </template>
      </dl>

      <div v-if="detail.configSnippet">
        <div class="flex items-center justify-between">
          <span class="text-[10px] font-bold opacity-70">{{
            t('hardwareBrowser.drivers.config')
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
        <a
          v-if="detail.configSource"
          :href="detail.configSource"
          target="_blank"
          rel="noopener noreferrer"
          class="text-[9px] underline opacity-60"
        >
          {{ t('hardwareBrowser.drivers.reference') }}
        </a>
      </div>

      <!-- cross-entity links (the boards that carry / support this driver) -->
      <RelatedChips :id="detail.driver_id" type="drivers" />
    </template>
  </EntityCatalog>
</template>
