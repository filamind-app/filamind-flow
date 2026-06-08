<script setup lang="ts">
/** Generic category catalog view — the remaining categories (sensors, hotends, extruders,
 *  fans/power/bed, displays/cameras, motion, nozzles, filament, electronics). Thin wrapper over
 *  the shared EntityCatalog; re-mounts per category via :key so each switch starts fresh. */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'

import { fetchCatalog, fetchCatalogEntity } from './api'
import EntityCatalog from './EntityCatalog.vue'
import RelatedChips from './RelatedChips.vue'
import type { CatalogEntityDetail, CatalogSummary } from './types'
import type { FocusTarget } from './useEntityFocus'
import { useFacets } from './useFacets'

const props = defineProps<{ category: string }>()
const emit = defineEmits<{ (e: 'back'): void }>()

const { t } = useI18n({ useScope: 'global' })

const manufacturer = ref('')
const subsection = ref<string | null>(null)
const reloadToken = ref(0)
const { facets } = useFacets()
/** Sub-type options for THIS category (the catalog equivalent of a board's class). */
const subsectionOptions = computed(() =>
  (facets.value?.catalogSubsections?.[props.category] ?? []).map((s) => ({ value: s, label: s })),
)
function onFacetChange(): void {
  reloadToken.value += 1
}

async function fetchPage(p: { q: string; offset: number; limit: number }) {
  const r = await fetchCatalog({
    category: props.category,
    q: p.q,
    manufacturer: manufacturer.value,
    subsection: subsection.value ?? '',
    limit: p.limit,
    offset: p.offset,
  })
  return { items: r.entities, total: r.total }
}
const idOf = (e: CatalogSummary): string => e.catalog_id
const focusMatch = (f: FocusTarget): boolean =>
  f.tab === 'category' && f.category === props.category
</script>

<template>
  <EntityCatalog
    :key="category"
    :fetch-page="fetchPage"
    :fetch-detail="fetchCatalogEntity"
    :id-of="idOf"
    :focus-match="focusMatch"
    :reload-token="reloadToken"
    search-key="hardwareBrowser.search.placeholder"
    total-key="hardwareBrowser.results.total"
    none-key="hardwareBrowser.results.none"
  >
    <template #facets>
      <div v-if="subsectionOptions.length" class="min-w-[9rem]">
        <ComboSelect
          v-model="subsection"
          :options="subsectionOptions"
          :placeholder="t('hardwareBrowser.facets.anyType')"
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

    <template #header>
      <div class="flex flex-wrap items-center gap-2">
        <button class="nb-btn bg-surface px-2 py-1 text-[11px]" @click="emit('back')">
          ‹ {{ t('hardwareBrowser.catalog.back') }}
        </button>
        <span class="font-bold">{{ category }}</span>
      </div>
    </template>

    <template
      #summary="{ item, open, toggle }: { item: CatalogSummary; open: boolean; toggle: () => void }"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate font-bold">{{ item.name }}</div>
          <div class="font-mono text-[10px] opacity-60">
            <span v-if="item.manufacturer">{{ item.manufacturer }} · </span>{{ item.subsection }}
          </div>
        </div>
        <button class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]" @click="toggle">
          {{ open ? t('hardwareBrowser.boards.hide') : t('hardwareBrowser.boards.view') }}
        </button>
      </div>
    </template>

    <template
      #detail="{
        detail,
        copied,
        copy,
      }: {
        detail: CatalogEntityDetail
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

      <!-- cross-entity links (its manufacturer) -->
      <RelatedChips :id="detail.catalog_id" type="catalog" />
    </template>
  </EntityCatalog>
</template>
