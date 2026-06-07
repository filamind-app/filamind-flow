<script setup lang="ts">
/** Generic category catalog view — used for the remaining categories (sensors, hotends,
 *  extruders, fans/power/bed, displays/cameras, motion, nozzles, filament, electronics).
 *  Each entity is deduped + carries a copyable Klipper config snippet. Mirrors BoardsPanel. */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchCatalog, fetchCatalogEntity } from './api'
import RelatedChips from './RelatedChips.vue'
import type { CatalogEntityDetail, CatalogSummary } from './types'
import { useEntityFocus } from './useEntityFocus'

const props = defineProps<{ category: string }>()
const emit = defineEmits<{ (e: 'back'): void }>()

const { t } = useI18n({ useScope: 'global' })
const LIMIT = 24

const q = ref('')
const entities = ref<CatalogSummary[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const openId = ref<string | null>(null)
const detailCache = ref<Record<string, CatalogEntityDetail>>({})
const detailLoading = ref<string | null>(null)

const hasNext = computed(() => offset.value + entities.value.length < total.value)
const hasPrev = computed(() => offset.value > 0)

async function load(reset = true): Promise<void> {
  if (reset) offset.value = 0
  loading.value = true
  try {
    const r = await fetchCatalog({
      category: props.category,
      q: q.value,
      limit: LIMIT,
      offset: offset.value,
    })
    entities.value = r.entities
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
      detailCache.value[id] = await fetchCatalogEntity(id)
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

// deep-link: when a cross-link chip targets a catalog entity in THIS category, surface + open it
const { focus } = useEntityFocus()
async function applyFocus(): Promise<void> {
  const f = focus.value
  if (!f || f.tab !== 'category' || f.category !== props.category) return
  q.value = f.name ?? ''
  await load(true)
  if (openId.value !== f.id && entities.value.some((e) => e.catalog_id === f.id)) void toggle(f.id)
}

// reload when the chosen category changes
watch(
  () => props.category,
  () => {
    q.value = ''
    openId.value = null
    void load(true).then(applyFocus)
  },
)
watch(focus, () => void applyFocus())
onMounted(() => void load(true).then(applyFocus))
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <button class="nb-btn bg-surface px-2 py-1 text-[11px]" @click="emit('back')">
        ‹ {{ t('hardwareBrowser.catalog.back') }}
      </button>
      <span class="font-bold">{{ category }}</span>
    </div>

    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.search.placeholder')
        }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t('hardwareBrowser.search.placeholder')"
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

    <p v-if="loading && !entities.length" class="font-mono text-xs opacity-70">
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
        {{ t('hardwareBrowser.results.total', { count: total }) }}
      </p>
      <p v-if="!entities.length" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.results.none') }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="e in entities" :key="e.catalog_id" class="nb-card bg-surface p-2">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ e.name }}</div>
              <div class="font-mono text-[10px] opacity-60">
                <span v-if="e.manufacturer">{{ e.manufacturer }} · </span>{{ e.subsection }}
              </div>
            </div>
            <button
              class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggle(e.catalog_id)"
            >
              {{
                openId === e.catalog_id
                  ? t('hardwareBrowser.boards.hide')
                  : t('hardwareBrowser.boards.view')
              }}
            </button>
          </div>

          <div v-if="openId === e.catalog_id" class="mt-2 space-y-2 border-t-2 border-ink pt-2">
            <p v-if="detailLoading === e.catalog_id" class="font-mono text-[11px] opacity-70">
              {{ t('boardTopology.board.loading') }}
            </p>
            <template v-else-if="detailCache[e.catalog_id]">
              <!-- specs -->
              <dl
                v-if="Object.keys(detailCache[e.catalog_id].specs || {}).length"
                class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]"
              >
                <template v-for="(val, key) in detailCache[e.catalog_id].specs" :key="key">
                  <dt class="opacity-60">{{ key }}</dt>
                  <dd class="min-w-0">{{ val }}</dd>
                </template>
              </dl>

              <!-- copy-ready config snippet -->
              <div v-if="detailCache[e.catalog_id].configSnippet">
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-bold opacity-70">{{
                    t('hardwareBrowser.boards.config')
                  }}</span>
                  <button
                    class="nb-btn bg-brand-lime px-2 py-0 text-[9px]"
                    @click="copyConfig(e.catalog_id, detailCache[e.catalog_id].configSnippet || '')"
                  >
                    {{
                      copied === e.catalog_id
                        ? t('hardwareBrowser.boards.copied')
                        : t('hardwareBrowser.boards.copy')
                    }}
                  </button>
                </div>
                <pre
                  class="overflow-x-auto rounded-brutal border-2 border-ink bg-paper p-2 text-[9px] leading-tight"
                  >{{ detailCache[e.catalog_id].configSnippet }}</pre
                >
              </div>

              <!-- cross-entity links (its manufacturer) -->
              <RelatedChips :id="e.catalog_id" type="catalog" />
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
