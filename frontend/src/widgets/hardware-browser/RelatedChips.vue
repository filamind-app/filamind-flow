<script setup lang="ts">
/** Clickable cross-link chips for one entity — the visible face of the DB linking graph.
 *  Fetches `GET /api/hardware/{type}/{id}/related` and renders its grouped neighbours as chips;
 *  clicking a chip jumps the browser to that entity (via the shared entity-focus channel). */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchRelated } from './api'
import type { RelatedRef, RelatedResult } from './types'
import { targetFor, useEntityFocus } from './useEntityFocus'

const props = defineProps<{
  /** Plural route type: boards / drivers / motors / hosts / catalog / manufacturers / mcus. */
  type: string
  id: string
}>()

const { t } = useI18n({ useScope: 'global' })
const { focusEntity } = useEntityFocus()

/** Fixed display order; only groups actually present are rendered. */
const REL_ORDER = [
  'manufacturer',
  'mcus',
  'onboardDrivers',
  'supportedDrivers',
  'boards',
  'motors',
  'hosts',
  'catalog',
] as const
const MAX_CHIPS = 14

const related = ref<RelatedResult | null>(null)
const loading = ref(false)

async function load(): Promise<void> {
  related.value = null
  if (!props.id || !props.type) return
  loading.value = true
  try {
    related.value = await fetchRelated(props.type, props.id)
  } catch {
    related.value = null
  } finally {
    loading.value = false
  }
}

watch(() => [props.type, props.id], load, { immediate: true })

const groups = computed(() => {
  const r = related.value
  if (!r) return []
  return REL_ORDER.filter((rel) => (r.groups[rel] || []).length).map((rel) => ({
    rel,
    label: t(`hardwareBrowser.related.rel.${rel}`),
    items: r.groups[rel],
    count: r.counts[rel] ?? r.groups[rel].length,
  }))
})

const hasAny = computed(() => groups.value.length > 0)

function chipLabel(entry: RelatedRef): string {
  return entry.name || entry.id
}

function open(entry: RelatedRef): void {
  const target = targetFor(entry)
  if (target) focusEntity(target)
}
</script>

<template>
  <div v-if="loading" class="font-mono text-[10px] opacity-50">
    {{ t('hardwareBrowser.related.loading') }}
  </div>
  <div v-else-if="hasAny" class="space-y-1">
    <div class="text-[10px] font-bold opacity-70">{{ t('hardwareBrowser.related.title') }}</div>
    <div v-for="g in groups" :key="g.rel" class="flex flex-wrap items-baseline gap-1">
      <span class="shrink-0 font-mono text-[9px] opacity-60">{{ g.label }}:</span>
      <button
        v-for="entry in g.items.slice(0, MAX_CHIPS)"
        :key="entry.type + ':' + entry.id"
        type="button"
        class="nb-btn bg-paper px-1.5 py-0 text-[9px] hover:bg-brand-cyan/30"
        :title="t('hardwareBrowser.related.jump', { name: chipLabel(entry) })"
        @click="open(entry)"
      >
        {{ chipLabel(entry) }}
      </button>
      <span v-if="g.count > MAX_CHIPS" class="font-mono text-[9px] opacity-50">
        {{ t('hardwareBrowser.related.more', { n: g.count - MAX_CHIPS }) }}
      </span>
    </div>
  </div>
</template>
