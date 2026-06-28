<script setup lang="ts">
/** Host Control · Advisor - graded host-health cards.
 *
 *  A one-glance read of the host's OS health (CPU temp/throttle, memory + swap, disk, clock/NTP,
 *  print-stack services), each graded A-F with status badges and an actionable fix hint. Read-only:
 *  the same signals the Monitor shows, scored per card. Mirrors the Machine Doctor card idiom. */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import { describeError } from '@/core/describeError'

import { fetchAdvisor } from './api'
import type { HealthCard } from './types'

const { t, te } = useI18n({ useScope: 'global' })

const cards = ref<HealthCard[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  if (!cards.value.length) loading.value = true
  error.value = null
  try {
    cards.value = (await fetchAdvisor()).cards
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const GRADE_BG: Record<string, string> = {
  A: 'bg-brand-lime',
  B: 'bg-brand-cyan',
  C: 'bg-brand-yellow',
  D: 'bg-brand-pink',
  F: 'bg-brand-red',
}
const STATUS_BAR: Record<string, string> = {
  ok: 'bg-brand-lime',
  warn: 'bg-brand-yellow',
  fail: 'bg-brand-red',
  unknown: 'bg-ink/30',
}
const STATUS_ICON: Record<string, string> = { ok: '✓', warn: '⚠', fail: '✕', unknown: '?' }

const cardTitle = (id: string): string =>
  te('hostControl.advisor.card.' + id) ? t('hostControl.advisor.card.' + id) : id
const badgeLabel = (code: string): string =>
  te('hostControl.advisor.badge.' + code) ? t('hostControl.advisor.badge.' + code) : code
const hint = (code: string | null): string =>
  code && te('hostControl.advisor.hint.' + code) ? t('hostControl.advisor.hint.' + code) : ''
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('hostControl.advisor.intro') }}</p>
      <button type="button" class="nb-btn text-xs" :disabled="loading" @click="load">
        ↻ {{ t('hostControl.monitor.refresh') }}
      </button>
    </div>

    <div
      v-if="error"
      role="alert"
      class="nb-card flex items-start justify-between gap-2 bg-brand-red/10 p-2 font-mono text-xs"
    >
      <span class="min-w-0 wrap-break-word">{{ error }}</span>
      <ReportErrorButton :error="error" />
    </div>

    <p v-if="loading && !cards.length" class="font-mono text-[11px] opacity-60">
      {{ t('hostControl.monitor.loading') }}
    </p>

    <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <section v-for="c in cards" :key="c.id" class="nb-card space-y-1.5 bg-surface p-3">
        <div class="flex items-center justify-between gap-2">
          <h3 class="text-xs font-bold uppercase tracking-wide opacity-70">
            {{ cardTitle(c.id) }}
          </h3>
          <span
            class="rounded-sm border border-ink px-1.5 text-[11px] font-bold text-ink"
            :class="GRADE_BG[c.grade] ?? 'bg-ink/10'"
          >
            {{ c.grade }}
          </span>
        </div>

        <!-- score bar -->
        <div class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper">
          <div
            class="h-full"
            :class="STATUS_BAR[c.status] ?? 'bg-ink/30'"
            :style="{ width: c.score + '%' }"
          />
        </div>

        <div class="flex items-center gap-1.5 font-mono text-[11px]">
          <span
            :class="
              c.status === 'fail'
                ? 'text-brand-red'
                : c.status === 'warn'
                  ? 'text-brand-yellow'
                  : c.status === 'ok'
                    ? 'text-brand-lime'
                    : 'opacity-60'
            "
            >{{ STATUS_ICON[c.status] }} {{ t('hostControl.advisor.status.' + c.status) }}</span
          >
          <span class="opacity-50" dir="ltr">· {{ c.detail }}</span>
        </div>

        <!-- badges -->
        <div v-if="c.badges.length" class="flex flex-wrap gap-1">
          <span
            v-for="b in c.badges"
            :key="b"
            class="rounded-sm bg-brand-red/15 px-1 text-[10px] font-bold"
          >
            {{ badgeLabel(b) }}
          </span>
        </div>

        <!-- fix hint -->
        <p v-if="hint(c.fix_code)" class="text-[11px] opacity-70">{{ hint(c.fix_code) }}</p>
      </section>
    </div>
  </div>
</template>
