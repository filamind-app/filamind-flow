<script setup lang="ts">
/** Pin Atlas — an X-ray of a board's pins: which the live config uses (and for what) vs which are
 *  free, grouped by function, plus a wiring-conflict scanner (double-assigned pins, electronics
 *  caveats bound to a used pin). Read-only over `GET /api/topology/pin-atlas/{mcu_name}`. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useNav } from '@/core/nav'
import { focusConfigSection } from '@/widgets/config-editor/configFocus'

import { fetchPinAtlas } from './api'
import type { PinAtlas, PinAtlasPin } from './types'

const props = defineProps<{ mcuName: string }>()

const { t } = useI18n({ useScope: 'global' })
const { go } = useNav()

/** Jump from a wiring finding straight to the offending section in the Config Editor. */
function openSection(owner: string): void {
  const dot = owner.lastIndexOf('.')
  focusConfigSection(dot > 0 ? owner.slice(0, dot) : owner)
  go('config-editor')
}

const atlas = ref<PinAtlas | null>(null)
const loading = ref(false)
const failed = ref(false)
const query = ref('')
const freeOnly = ref(false)

watch(
  () => props.mcuName,
  async (name) => {
    atlas.value = null
    failed.value = false
    if (!name) return
    loading.value = true
    try {
      atlas.value = await fetchPinAtlas(name)
    } catch {
      failed.value = true
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

function matches(p: PinAtlasPin): boolean {
  if (freeOnly.value && p.used) return false
  const q = query.value.trim().toLowerCase()
  if (!q) return true
  return [p.pin, p.signal, p.config_key, p.port, ...p.owners].some((s) =>
    (s || '').toLowerCase().includes(q),
  )
}

/** Pins grouped by their port category, filtered by the search / free-only controls. */
const groups = computed(() => {
  const out = new Map<string, PinAtlasPin[]>()
  for (const p of atlas.value?.pins ?? []) {
    if (!matches(p)) continue
    const cat = p.category || t('boardTopology.pinAtlas.other')
    if (!out.has(cat)) out.set(cat, [])
    out.get(cat)!.push(p)
  }
  return [...out.entries()].sort((a, b) => a[0].localeCompare(b[0]))
})

const usedPct = computed(() => {
  const a = atlas.value
  return a && a.total ? Math.round((a.used / a.total) * 100) : 0
})

function pinTitle(p: PinAtlasPin): string {
  const bits = [p.pin, p.signal, p.port].filter(Boolean).join(' · ')
  const own = p.owners.length ? '\n→ ' + p.owners.join(', ') : ''
  const cav = p.caveat ? '\n⚠ ' + p.caveat : ''
  return bits + own + cav
}
</script>

<template>
  <div class="space-y-2 text-[11px]">
    <p v-if="loading" class="font-mono opacity-70">{{ t('boardTopology.pinAtlas.loading') }}</p>
    <p v-else-if="failed" class="font-mono opacity-70">{{ t('boardTopology.pinAtlas.failed') }}</p>
    <p v-else-if="!atlas || !atlas.available" class="opacity-60">
      {{ t('boardTopology.pinAtlas.unavailable') }}
    </p>

    <template v-else>
      <!-- summary + usage bar -->
      <div class="space-y-1">
        <div class="flex items-center justify-between font-mono">
          <span class="font-bold">{{ atlas.board_name }}</span>
          <span class="opacity-70">{{
            t('boardTopology.pinAtlas.summary', {
              used: atlas.used,
              total: atlas.total,
              free: atlas.free,
            })
          }}</span>
        </div>
        <div
          class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper"
          role="img"
          :aria-label="
            t('boardTopology.pinAtlas.summary', {
              used: atlas.used,
              total: atlas.total,
              free: atlas.free,
            })
          "
        >
          <div class="h-full bg-brand-lime" :style="{ width: usedPct + '%' }"></div>
        </div>
      </div>

      <!-- wiring-health findings -->
      <ul v-if="atlas.findings.length" class="space-y-1">
        <li
          v-for="(f, i) in atlas.findings"
          :key="i"
          class="rounded border-l-4 p-1"
          :class="
            f.kind === 'double_assign'
              ? 'border-brand-red bg-brand-red/10'
              : 'border-brand-yellow bg-brand-yellow/15'
          "
        >
          <span class="font-bold">{{
            f.kind === 'double_assign'
              ? '✕ ' + t('boardTopology.pinAtlas.conflict')
              : '⚠ ' + t('boardTopology.pinAtlas.caveat')
          }}</span>
          · <span class="font-mono font-bold">{{ f.pin }}</span> — {{ f.message }}
          <span v-if="f.sections.length" class="mt-0.5 flex flex-wrap gap-1">
            <button
              v-for="sec in f.sections"
              :key="sec"
              class="rounded border border-ink/40 bg-surface px-1 font-mono text-[10px] hover:bg-ink/10"
              :title="t('boardTopology.jump.section')"
              @click="openSection(sec)"
            >
              {{ sec }} ↗
            </button>
          </span>
        </li>
      </ul>

      <!-- controls -->
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="query"
          type="search"
          class="flex-1 rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-[11px]"
          :placeholder="t('boardTopology.pinAtlas.search')"
          :aria-label="t('boardTopology.pinAtlas.search')"
        />
        <label class="inline-flex cursor-pointer items-center gap-1">
          <input v-model="freeOnly" type="checkbox" />
          {{ t('boardTopology.pinAtlas.freeOnly') }}
        </label>
      </div>

      <!-- pin grid grouped by function -->
      <p v-if="!groups.length" class="opacity-60">{{ t('boardTopology.pinAtlas.noMatch') }}</p>
      <div v-for="[cat, pins] in groups" :key="cat" class="space-y-0.5">
        <div class="font-mono text-[10px] uppercase opacity-50">{{ cat }}</div>
        <div class="flex flex-wrap gap-1">
          <span
            v-for="p in pins"
            :key="p.pin"
            class="inline-flex items-center gap-0.5 rounded border px-1 py-0.5 font-mono text-[10px]"
            :class="
              p.used
                ? p.caveat
                  ? 'border-ink bg-brand-yellow/60'
                  : 'border-ink bg-brand-lime/60'
                : 'border-ink/30 bg-paper opacity-60'
            "
            :title="pinTitle(p)"
          >
            <span class="font-bold">{{ p.pin }}</span>
            <span v-if="p.caveat" aria-hidden="true">⚠</span>
            <span v-if="p.used && p.signal" class="opacity-70">{{ p.signal }}</span>
          </span>
        </div>
      </div>
    </template>
  </div>
</template>
