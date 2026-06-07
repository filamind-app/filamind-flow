<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import { describeError } from '@/core/describeError'

import { fetchCategories, searchHardware } from './api'
import BoardsPanel from './BoardsPanel.vue'
import CategoryIllo from './CategoryIllo.vue'
import DriversPanel from './DriversPanel.vue'
import MotorsPanel from './MotorsPanel.vue'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { HardwareSearchResult } from './types'

const LIMIT = 25
const { t } = useI18n({ useScope: 'global' })

type Mode = 'catalog' | 'boards' | 'drivers' | 'motors' | 'search'
const mode = ref<Mode>('catalog')
const TABS = computed(() => [
  { id: 'catalog' as Mode, label: t('hardwareBrowser.tabs.catalog') },
  { id: 'boards' as Mode, label: t('hardwareBrowser.tabs.boards') },
  { id: 'drivers' as Mode, label: t('hardwareBrowser.tabs.drivers') },
  { id: 'motors' as Mode, label: t('hardwareBrowser.tabs.motors') },
  { id: 'search' as Mode, label: t('hardwareBrowser.tabs.search') },
])

const q = ref('')
const category = ref<string | null>(null)
const manufacturer = ref('')
const offset = ref(0)
const result = ref<HardwareSearchResult | null>(null)
const categories = ref<string[]>([])
const counts = ref<Record<string, number>>({})
const totalCount = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const categoryOptions = computed(() => categories.value.map((c) => ({ value: c, label: c })))

/** Enter the right view for a category tile. The boards category opens the rich
 *  board catalog; everything else opens the flat Search pre-filtered. */
function openCategory(cat: string | null): void {
  const c = (cat ?? '').toLowerCase()
  if (c.includes('mcu') && c.includes('board')) {
    mode.value = 'boards'
    return
  }
  if (c.includes('driver')) {
    mode.value = 'drivers'
    return
  }
  if (c.includes('stepper') && c.includes('motor')) {
    mode.value = 'motors'
    return
  }
  category.value = cat
  q.value = ''
  manufacturer.value = ''
  mode.value = 'search'
  void doSearch(true)
}
const hasPrev = computed(() => offset.value > 0)
const hasNext = computed(() => {
  const r = result.value
  return !!r && r.offset + r.count < r.total
})
const showingFrom = computed(() => (result.value && result.value.count ? offset.value + 1 : 0))
const showingTo = computed(() => (result.value ? offset.value + result.value.count : 0))

async function doSearch(reset = true): Promise<void> {
  if (reset) offset.value = 0
  loading.value = true
  try {
    result.value = await searchHardware({
      q: q.value,
      category: category.value ?? '',
      manufacturer: manufacturer.value,
      limit: LIMIT,
      offset: offset.value,
    })
    error.value = null
  } catch (e) {
    error.value = describeError(e)
    result.value = null
  } finally {
    loading.value = false
  }
}

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * LIMIT)
  void doSearch(false)
}

watch(category, () => {
  if (mode.value === 'search') void doSearch(true)
})

onMounted(() => {
  fetchCategories()
    .then((c) => {
      categories.value = c.categories
      counts.value = c.counts ?? {}
      totalCount.value = c.total
    })
    .catch(() => {})
  void doSearch(true)
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('hardwareBrowser.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="hardwareBrowser"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="hardwareBrowser.help.steps"
          :button-label="t('hardwareBrowser.help.guide')"
          :title="t('hardwareBrowser.help.guideTitle')"
          :close-label="t('hardwareBrowser.help.close')"
          :steps-title="t('hardwareBrowser.help.howToRead')"
        />
        <HelpIllo illo="search" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <WidgetTabs v-model="mode" :tabs="TABS" />

    <!-- Catalog: one tile per category + a "search all" tile -->
    <div v-show="mode === 'catalog'" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <button
        class="nb-card flex flex-col items-center gap-1 bg-brand-yellow p-3 text-center"
        @click="openCategory(null)"
      >
        <span class="text-2xl" aria-hidden="true">🔍</span>
        <span class="text-xs font-bold">{{ t('hardwareBrowser.catalog.searchAll') }}</span>
        <span class="font-mono text-[10px] opacity-70">{{
          t('hardwareBrowser.catalog.items', { n: totalCount })
        }}</span>
      </button>
      <button
        v-for="cat in categories"
        :key="cat"
        class="nb-card flex flex-col items-center gap-1 bg-surface p-3 text-center hover:bg-brand-cyan/20"
        @click="openCategory(cat)"
      >
        <CategoryIllo :category="cat" class="h-8 w-8 text-ink" />
        <span class="text-[11px] font-bold leading-tight">{{ cat }}</span>
        <span class="font-mono text-[10px] opacity-70">{{
          t('hardwareBrowser.catalog.items', { n: counts[cat] ?? 0 })
        }}</span>
      </button>
    </div>

    <!-- Boards: the canonical board catalog (specs + ports + media) -->
    <BoardsPanel v-show="mode === 'boards'" />

    <!-- Drivers: the canonical driver catalog (specs + copyable [tmcXXXX] config) -->
    <DriversPanel v-show="mode === 'drivers'" />

    <!-- Motors: the canonical motor catalog (specs + recommended run_current + config) -->
    <MotorsPanel v-show="mode === 'motors'" />

    <!-- Search controls -->
    <div v-show="mode === 'search'" class="flex flex-wrap items-end gap-2">
      <label class="min-w-[10rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.search.placeholder')
        }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t('hardwareBrowser.search.placeholder')"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
          @keyup.enter="doSearch(true)"
        />
      </label>
      <label class="min-w-[9rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.search.manufacturer')
        }}</span>
        <input
          v-model="manufacturer"
          type="text"
          :placeholder="t('hardwareBrowser.search.manufacturerPlaceholder')"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
          @keyup.enter="doSearch(true)"
        />
      </label>
      <label class="min-w-[10rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.search.category')
        }}</span>
        <ComboSelect
          v-model="category"
          :options="categoryOptions"
          :placeholder="t('hardwareBrowser.search.allCategories')"
          clearable
        />
      </label>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
        :disabled="loading"
        @click="doSearch(true)"
      >
        {{ t('hardwareBrowser.search.button') }}
      </button>
    </div>

    <!-- States + results (search view only) -->
    <div v-show="mode === 'search'" class="space-y-3">
      <p v-if="loading && !result" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.states.loading') }}
      </p>
      <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
        <p class="font-mono text-xs">{{ t('hardwareBrowser.states.error') }}</p>
        <p class="font-mono text-[11px] opacity-70">{{ error }}</p>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="doSearch(false)">
          {{ t('hardwareBrowser.states.retry') }}
        </button>
      </div>

      <!-- Results -->
      <template v-if="result && !error">
        <div class="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px]">
          <span class="nb-card bg-surface px-2 py-0.5">
            {{ t('hardwareBrowser.results.total', { count: result.total }) }}
          </span>
          <span v-if="result.count" class="opacity-60">
            {{
              t('hardwareBrowser.results.showing', {
                from: showingFrom,
                to: showingTo,
                total: result.total,
              })
            }}
          </span>
        </div>

        <p v-if="!result.count" class="font-mono text-xs opacity-70">
          {{ t('hardwareBrowser.results.none') }}
        </p>

        <ul v-else class="space-y-2">
          <li v-for="(item, i) in result.items" :key="i" class="nb-card space-y-1 bg-surface p-2">
            <div class="flex flex-wrap items-baseline justify-between gap-x-2">
              <span class="font-bold">
                <span class="opacity-70">{{ item.manufacturer }}</span>
                <span v-if="item.name"> · {{ item.name }}</span>
              </span>
              <span
                class="shrink-0 rounded bg-brand-cyan px-1.5 py-0.5 text-[10px] font-bold text-ink"
              >
                {{ item.category }}
              </span>
            </div>
            <dl class="grid grid-cols-1 gap-x-3 gap-y-0.5 font-mono text-[10px] sm:grid-cols-2">
              <div v-for="(val, key) in item.specs" :key="key" class="flex gap-1">
                <dt class="shrink-0 opacity-60">{{ key }}:</dt>
                <dd class="min-w-0">{{ val }}</dd>
              </div>
            </dl>
          </li>
        </ul>

        <!-- Pagination -->
        <div v-if="result.total > result.limit" class="flex items-center justify-center gap-2">
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
  </div>
</template>
