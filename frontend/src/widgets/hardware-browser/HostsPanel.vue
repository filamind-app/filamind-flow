<script setup lang="ts">
/** The host catalog view: SBC / x86 / OS-image, with a copyable Klipper HOST config
 *  ([mcu host] block). Thin wrapper over the shared EntityCatalog. */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'

import { fetchHostDetail, fetchHosts } from './api'
import EntityCatalog from './EntityCatalog.vue'
import RelatedChips from './RelatedChips.vue'
import type { HostDetail, HostSummary } from './types'
import type { FocusTarget } from './useEntityFocus'
import { useFacets } from './useFacets'

const { t } = useI18n({ useScope: 'global' })

const kind = ref<string | null>(null)
const manufacturer = ref('')
const reloadToken = ref(0)
const { facets } = useFacets()
const kindOptions = computed(() =>
  (facets.value?.kind ?? []).map((v) => ({
    value: v,
    label: t(`hardwareBrowser.hosts.kind.${v}`),
  })),
)
function onFacetChange(): void {
  reloadToken.value += 1
}

async function fetchPage(p: { q: string; offset: number; limit: number }) {
  const r = await fetchHosts({
    q: p.q,
    manufacturer: manufacturer.value,
    kind: kind.value ?? '',
    limit: p.limit,
    offset: p.offset,
  })
  return { items: r.hosts, total: r.total }
}
const idOf = (h: HostSummary): string => h.host_id
const focusMatch = (f: FocusTarget): boolean => f.tab === 'hosts'
</script>

<template>
  <EntityCatalog
    :fetch-page="fetchPage"
    :fetch-detail="fetchHostDetail"
    :id-of="idOf"
    :focus-match="focusMatch"
    :reload-token="reloadToken"
    search-key="hardwareBrowser.hosts.search"
    total-key="hardwareBrowser.hosts.total"
    none-key="hardwareBrowser.hosts.none"
  >
    <template #facets>
      <div class="min-w-[8rem]">
        <ComboSelect
          v-model="kind"
          :options="kindOptions"
          :placeholder="t('hardwareBrowser.facets.anyKind')"
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
      #summary="{ item, open, toggle }: { item: HostSummary; open: boolean; toggle: () => void }"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate font-bold">{{ item.name }}</div>
          <div class="font-mono text-[10px] opacity-60">
            <span v-if="item.soc">{{ item.soc }}</span
            ><span v-if="item.ram"> · {{ item.ram }}</span>
          </div>
        </div>
        <button class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]" @click="toggle">
          {{ open ? t('hardwareBrowser.boards.hide') : t('hardwareBrowser.boards.view') }}
        </button>
      </div>
      <div class="mt-1 flex flex-wrap gap-1">
        <span
          class="rounded px-1 font-mono text-[9px]"
          :class="item.klipperOpen ? 'bg-brand-lime' : 'bg-paper opacity-70'"
        >
          {{ t(`hardwareBrowser.hosts.kind.${item.kind}`) }}
        </span>
        <span v-if="item.klipperOs" class="rounded bg-paper px-1 font-mono text-[9px]">
          {{ item.klipperOs }}
        </span>
      </div>
    </template>

    <template
      #detail="{
        detail,
        copied,
        copy,
      }: {
        detail: HostDetail
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
            t('hardwareBrowser.hosts.config')
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
      <RelatedChips :id="detail.host_id" type="hosts" />
    </template>
  </EntityCatalog>
</template>
