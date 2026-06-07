<script setup lang="ts" generic="TSummary, TDetail">
/** The shared shell for a paginated, expandable hardware catalog (DB-3b).
 *
 * Owns the boilerplate every detail panel repeated near-verbatim: the search box, an optional
 * facet area, the result list, pagination, per-row expand with a detail cache, the copy-config
 * helper, loading / error states, and cross-link deep-link focus. Each per-type panel becomes a
 * thin wrapper that supplies a `fetchPage` / `fetchDetail` closure and renders its own bespoke
 * summary + detail markup through slots, so nothing type-specific moves into here.
 */
import { computed, onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import type { FocusTarget } from './useEntityFocus'
import { useEntityFocus } from './useEntityFocus'

const props = withDefaults(
  defineProps<{
    /** Fetch one page. Server-paginated panels hit the API; the contract is uniform. */
    fetchPage: (params: { q: string; offset: number; limit: number }) => Promise<{
      items: TSummary[]
      total: number
    }>
    /** Fetch a row's full record (lazy, cached). */
    fetchDetail: (id: string) => Promise<TDetail>
    /** Extract a row's stable id. */
    idOf: (item: TSummary) => string
    /** i18n keys (called with both {n} and {count} so either placeholder works). */
    searchKey: string
    totalKey: string
    noneKey: string
    limit?: number
    /** Bump to force a reload + fresh search (facet / category change). */
    reloadToken?: number | string
    /** Return true when a cross-link focus targets this catalog (drives deep-link open). */
    focusMatch?: (f: FocusTarget) => boolean
    /** Run synchronously before a deep-link search — lets a wrapper clear its own facets so the
     *  target can't be filtered out (e.g. Drivers clears its Klipper-only checkbox). */
    beforeFocus?: () => void
  }>(),
  { limit: 24, reloadToken: 0, focusMatch: undefined, beforeFocus: undefined },
)

const { t } = useI18n({ useScope: 'global' })
const { focus } = useEntityFocus()

const q = ref('')
// cast past UnwrapRef so the generic TSummary / TDetail survive into the template + script
const items = ref([]) as Ref<TSummary[]>
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const openId = ref<string | null>(null)
const detailCache = ref({}) as Ref<Record<string, TDetail>>
const detailLoading = ref<string | null>(null)

const hasNext = computed(() => offset.value + items.value.length < total.value)
const hasPrev = computed(() => offset.value > 0)

async function load(reset = true): Promise<void> {
  if (reset) offset.value = 0
  loading.value = true
  try {
    const r = await props.fetchPage({ q: q.value, offset: offset.value, limit: props.limit })
    items.value = r.items
    total.value = r.total
    error.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * props.limit)
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
      detailCache.value[id] = await props.fetchDetail(id)
    } catch {
      openId.value = null
    } finally {
      detailLoading.value = null
    }
  }
}

const copied = ref<string | null>(null)
function copyConfig(id: string, text: string): void {
  void navigator.clipboard?.writeText(text)
  copied.value = id
  window.setTimeout(() => {
    if (copied.value === id) copied.value = null
  }, 1500)
}

/** Deep-link: surface a specific row (search by its name, then expand it once loaded). */
async function focusItem(id: string, name?: string): Promise<void> {
  props.beforeFocus?.() // clear wrapper facets first so the target isn't filtered out
  q.value = name ?? ''
  await load(true)
  if (openId.value !== id && items.value.some((it) => props.idOf(it) === id)) void toggle(id)
}

/** Re-run a fresh search (used by wrappers when a facet or the category changes). */
function reload(): void {
  q.value = ''
  openId.value = null
  void load(true)
}

// a facet change keeps the current query; only a context switch (category) clears it via reload()
watch(
  () => props.reloadToken,
  () => void load(true),
)

// post-mount focus changes (a cross-link chip clicked while already mounted)
watch(focus, (f) => {
  if (f && props.focusMatch?.(f)) void focusItem(f.id, f.name)
})

// at mount, if a focus already targets this catalog open it directly (single load, no race)
onMounted(() => {
  const f = focus.value
  if (f && props.focusMatch?.(f)) void focusItem(f.id, f.name)
  else void load(true)
})

defineExpose({ reload, focusItem })
</script>

<template>
  <div class="space-y-2 text-sm">
    <slot name="header" />

    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{ t(searchKey) }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t(searchKey)"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
          @keyup.enter="load(true)"
        />
      </label>
      <slot name="facets" />
      <button
        class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
        :disabled="loading"
        @click="load(true)"
      >
        {{ t('hardwareBrowser.search.button') }}
      </button>
    </div>

    <p v-if="loading && !items.length" class="font-mono text-xs opacity-70">
      {{ t('hardwareBrowser.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-[11px]">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load(false)">
        {{ t('hardwareBrowser.states.retry') }}
      </button>
    </div>

    <template v-else>
      <p class="font-mono text-[11px] opacity-60">{{ t(totalKey, { n: total, count: total }) }}</p>
      <p v-if="!items.length" class="font-mono text-xs opacity-70">
        {{ t(noneKey, { n: total, count: total }) }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="item in items" :key="idOf(item)" class="nb-card bg-surface p-2">
          <slot
            name="summary"
            :item="item"
            :open="openId === idOf(item)"
            :toggle="() => toggle(idOf(item))"
          />

          <div v-if="openId === idOf(item)" class="mt-2 space-y-2 border-t-2 border-ink pt-2">
            <p v-if="detailLoading === idOf(item)" class="font-mono text-[11px] opacity-70">
              {{ t('boardTopology.board.loading') }}
            </p>
            <slot
              v-else-if="detailCache[idOf(item)]"
              name="detail"
              :detail="detailCache[idOf(item)]"
              :copied="copied === idOf(item)"
              :copy="(text: string) => copyConfig(idOf(item), text)"
            />
          </div>
        </li>
      </ul>

      <div v-if="total > limit" class="flex items-center justify-center gap-2">
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
