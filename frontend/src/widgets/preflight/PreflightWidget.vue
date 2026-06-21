<script setup lang="ts">
/** Pre-print readiness gate (suite-only / flow-A). A read-only glance at whether the printer is
 *  ready to start a print: queries the backend's preflight checks and shows an overall ready/not
 *  banner plus a per-check list (hard blockers vs informational warnings).
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { getPreflight } from './api'
import type { PreflightResult } from './types'

const { t } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string

const result = ref<PreflightResult | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    result.value = await getPreflight()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function icon(ok: boolean, level: string): string {
  if (ok) return '✓' // check mark
  return level === 'error' ? '✗' : '⚠' // cross / warning sign
}

function tone(ok: boolean, level: string): string {
  if (ok) return 'bg-brand-lime'
  return level === 'error' ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('preflight.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="preflight"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('preflight.help.guide')"
        :title="t('preflight.help.guideTitle')"
        :close-label="t('preflight.help.close')"
      />
    </div>

    <div class="flex items-center gap-2">
      <button class="nb-btn bg-brand-cyan px-3 py-1" :disabled="loading" @click="refresh">
        {{ t('preflight.refresh') }}
      </button>
      <span v-if="loading" class="text-xs opacity-70">{{ t('preflight.checking') }}</span>
    </div>

    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>

    <template v-if="result">
      <!-- Overall verdict -->
      <p
        class="nb-card px-3 py-2 text-sm font-bold"
        :class="result.ready ? 'bg-brand-lime' : 'bg-brand-red text-paper'"
        role="status"
      >
        {{ result.ready ? t('preflight.ready') : t('preflight.notReady') }}
      </p>

      <!-- Per-check list -->
      <ul class="space-y-1.5">
        <li
          v-for="c in result.checks"
          :key="c.code"
          class="nb-card flex items-center gap-2 px-2 py-1 text-xs"
          :class="tone(c.ok, c.level)"
        >
          <span class="font-mono font-bold" aria-hidden="true">{{ icon(c.ok, c.level) }}</span>
          <span>{{ tt(`preflight.checks.${c.code}.${c.ok ? 'pass' : 'fail'}`, c.params) }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>
