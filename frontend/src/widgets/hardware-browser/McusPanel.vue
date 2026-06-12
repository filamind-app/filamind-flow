<script setup lang="ts">
/** Browse the canonical MCU entities (parsed from board specs). Expanding one shows the boards
 *  that use it via RelatedChips. Supports deep-link focus (open a specific MCU). */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchMcus } from './api'
import RelatedChips from './RelatedChips.vue'
import type { McuEntity } from './types'
import { useEntityFocus } from './useEntityFocus'

const { t } = useI18n({ useScope: 'global' })

const all = ref<McuEntity[]>([])
const q = ref('')
const openId = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const { focus } = useEntityFocus()

const filtered = computed(() => {
  const ql = q.value.trim().toLowerCase()
  if (!ql) return all.value
  return all.value.filter(
    (m) => m.name.toLowerCase().includes(ql) || m.family.toLowerCase().includes(ql),
  )
})

async function load(): Promise<void> {
  loading.value = true
  try {
    all.value = (await fetchMcus()).items
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

watch(
  focus,
  (f) => {
    if (f && f.tab === 'mcus') {
      q.value = ''
      if (all.value.length) openId.value = f.id
      else void load().then(() => (openId.value = f.id))
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
    <label class="block min-w-[12rem]">
      <span class="mb-0.5 block text-[11px] opacity-70">{{
        t('hardwareBrowser.mcus.search')
      }}</span>
      <input
        v-model="q"
        type="search"
        :placeholder="t('hardwareBrowser.mcus.search')"
        class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
      />
    </label>

    <p v-if="loading && !all.length" class="font-mono text-xs opacity-70">
      {{ t('hardwareBrowser.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p role="alert" class="font-mono text-[11px]">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load()">
        {{ t('hardwareBrowser.states.retry') }}
      </button>
    </div>

    <template v-else>
      <p class="font-mono text-[11px] opacity-60">
        {{ t('hardwareBrowser.mcus.total', { n: filtered.length }) }}
      </p>
      <p v-if="!filtered.length" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.mcus.none') }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="m in filtered" :key="m.mcu_id" class="nb-card bg-surface p-2">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ m.name }}</div>
              <div class="flex flex-wrap items-center gap-1 font-mono text-[10px] opacity-60">
                <span class="rounded bg-paper px-1">{{ m.family }}</span>
                <span v-if="m.arch">· {{ m.arch }}</span>
                <span class="rounded bg-brand-cyan px-1 text-ink">{{
                  t('hardwareBrowser.mcus.boards', { n: m.boardCount })
                }}</span>
              </div>
            </div>
            <button
              class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggle(m.mcu_id)"
            >
              {{
                openId === m.mcu_id
                  ? t('hardwareBrowser.boards.hide')
                  : t('hardwareBrowser.boards.view')
              }}
            </button>
          </div>

          <div v-if="openId === m.mcu_id" class="mt-2 space-y-2 border-t-2 border-ink pt-2">
            <RelatedChips :id="m.mcu_id" type="mcus" />
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>
