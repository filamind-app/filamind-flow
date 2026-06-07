<script setup lang="ts">
/** The motor catalog view: specs + a recommended Klipper run_current + a copyable config
 *  snippet. Thin wrapper over the shared EntityCatalog. */
import { useI18n } from 'vue-i18n'

import { fetchMotorDetail, fetchMotors } from './api'
import EntityCatalog from './EntityCatalog.vue'
import RelatedChips from './RelatedChips.vue'
import type { MotorDetail, MotorSummary } from './types'
import type { FocusTarget } from './useEntityFocus'

const { t } = useI18n({ useScope: 'global' })

async function fetchPage(p: { q: string; offset: number; limit: number }) {
  const r = await fetchMotors({ q: p.q, limit: p.limit, offset: p.offset })
  return { items: r.motors, total: r.total }
}
const idOf = (m: MotorSummary): string => m.motor_id
const focusMatch = (f: FocusTarget): boolean => f.tab === 'motors'
</script>

<template>
  <EntityCatalog
    :fetch-page="fetchPage"
    :fetch-detail="fetchMotorDetail"
    :id-of="idOf"
    :focus-match="focusMatch"
    search-key="hardwareBrowser.motors.search"
    total-key="hardwareBrowser.motors.total"
    none-key="hardwareBrowser.motors.none"
  >
    <template
      #summary="{ item, open, toggle }: { item: MotorSummary; open: boolean; toggle: () => void }"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="truncate font-bold">{{ item.name }}</div>
          <div class="font-mono text-[10px] opacity-60">
            <span v-if="item.manufacturer">{{ item.manufacturer }} · </span>NEMA {{ item.nema }} ·
            {{ item.stepAngle }}
          </div>
        </div>
        <button class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]" @click="toggle">
          {{ open ? t('hardwareBrowser.boards.hide') : t('hardwareBrowser.boards.view') }}
        </button>
      </div>
      <div class="mt-1 flex flex-wrap gap-1">
        <span v-if="item.ratedCurrent" class="rounded bg-paper px-1 font-mono text-[9px]">
          {{ t('hardwareBrowser.motors.rated') }} {{ item.ratedCurrent }}
        </span>
        <span
          v-if="item.recommendedRunCurrent"
          class="rounded bg-brand-lime px-1 font-mono text-[9px]"
        >
          {{ t('hardwareBrowser.motors.run') }} {{ item.recommendedRunCurrent }} A
        </span>
        <span v-if="item.holdingTorque" class="rounded bg-paper px-1 font-mono text-[9px]">
          {{ item.holdingTorque }}
        </span>
      </div>
    </template>

    <template
      #detail="{
        detail,
        copied,
        copy,
      }: {
        detail: MotorDetail
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
            t('hardwareBrowser.motors.config')
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
      <RelatedChips :id="detail.motor_id" type="motors" />
    </template>
  </EntityCatalog>
</template>
