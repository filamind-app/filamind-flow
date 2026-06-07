<script setup lang="ts">
/** Browse the canonical manufacturer entities (deduped, with memberCount). Expanding one shows
 *  its linked hardware via RelatedChips. Supports deep-link focus (open a specific manufacturer). */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchManufacturers } from './api'
import RelatedChips from './RelatedChips.vue'
import type { ManufacturerEntity } from './types'
import { useEntityFocus } from './useEntityFocus'

const { t } = useI18n({ useScope: 'global' })
const LIMIT = 24

const all = ref<ManufacturerEntity[]>([])
const q = ref('')
const offset = ref(0)
const openId = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const { focus } = useEntityFocus()

const filtered = computed(() => {
  const ql = q.value.trim().toLowerCase()
  if (!ql) return all.value
  return all.value.filter(
    (m) =>
      m.name.toLowerCase().includes(ql) ||
      (m.aliases || []).some((a) => a.toLowerCase().includes(ql)),
  )
})
const page = computed(() => filtered.value.slice(offset.value, offset.value + LIMIT))
const hasPrev = computed(() => offset.value > 0)
const hasNext = computed(() => offset.value + LIMIT < filtered.value.length)

async function load(): Promise<void> {
  loading.value = true
  try {
    all.value = await fetchManufacturers()
    error.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function toggle(id: string): void {
  openId.value = openId.value === id ? null : id
}

function paginate(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * LIMIT)
  openId.value = null
}

watch(q, () => {
  offset.value = 0
})

/** Deep-link: open a specific manufacturer (clear search, jump to its page, expand it). */
function focusById(id: string): void {
  q.value = ''
  const idx = all.value.findIndex((m) => m.manufacturer_id === id)
  if (idx >= 0) offset.value = Math.floor(idx / LIMIT) * LIMIT
  openId.value = id
}
watch(
  focus,
  (f) => {
    if (f && f.tab === 'manufacturers') {
      if (all.value.length) focusById(f.id)
      else void load().then(() => focusById(f.id))
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (!all.value.length) void load()
})
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.manufacturers.search')
        }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t('hardwareBrowser.manufacturers.search')"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
        />
      </label>
    </div>

    <p v-if="loading && !all.length" class="font-mono text-xs opacity-70">
      {{ t('hardwareBrowser.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-[11px]">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load()">
        {{ t('hardwareBrowser.states.retry') }}
      </button>
    </div>

    <template v-else>
      <p class="font-mono text-[11px] opacity-60">
        {{ t('hardwareBrowser.manufacturers.total', { n: filtered.length }) }}
      </p>
      <p v-if="!filtered.length" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.manufacturers.none') }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="m in page" :key="m.manufacturer_id" class="nb-card bg-surface p-2">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ m.name }}</div>
              <div class="flex flex-wrap items-center gap-1 font-mono text-[10px] opacity-60">
                <span class="rounded bg-brand-cyan px-1 text-ink">{{
                  t('hardwareBrowser.manufacturers.members', { n: m.memberCount })
                }}</span>
                <span v-if="m.country">· {{ m.country }}</span>
                <span v-if="m.origin === 'derived'" class="rounded bg-paper px-1">{{
                  t('hardwareBrowser.manufacturers.derived')
                }}</span>
              </div>
            </div>
            <button
              class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggle(m.manufacturer_id)"
            >
              {{
                openId === m.manufacturer_id
                  ? t('hardwareBrowser.boards.hide')
                  : t('hardwareBrowser.boards.view')
              }}
            </button>
          </div>

          <div
            v-if="openId === m.manufacturer_id"
            class="mt-2 space-y-2 border-t-2 border-ink pt-2"
          >
            <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]">
              <template v-if="m.specialty">
                <dt class="opacity-60">{{ t('hardwareBrowser.manufacturers.specialty') }}</dt>
                <dd>{{ m.specialty }}</dd>
              </template>
              <template v-if="m.aliases && m.aliases.length">
                <dt class="opacity-60">{{ t('hardwareBrowser.manufacturers.aliases') }}</dt>
                <dd>{{ m.aliases.join(', ') }}</dd>
              </template>
            </dl>
            <a
              v-if="m.website"
              :href="m.website"
              target="_blank"
              rel="noopener noreferrer"
              class="nb-btn inline-block bg-paper px-1 py-0 text-[9px]"
            >
              {{ t('hardwareBrowser.manufacturers.website') }}
            </a>
            <RelatedChips :id="m.manufacturer_id" type="manufacturers" />
          </div>
        </li>
      </ul>

      <div v-if="filtered.length > LIMIT" class="flex items-center justify-center gap-2">
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasPrev"
          @click="paginate(-1)"
        >
          ‹ {{ t('hardwareBrowser.results.prev') }}
        </button>
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasNext"
          @click="paginate(1)"
        >
          {{ t('hardwareBrowser.results.next') }} ›
        </button>
      </div>
    </template>
  </div>
</template>
