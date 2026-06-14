<script setup lang="ts">
/** Host Control · Disk cleanup — reclaim space from caches and rotated logs.
 *
 *  Every target is dry-run scanned first ("frees X"), the user ticks what to remove, and a single
 *  confirmation runs the delete. Only regenerable data is offered (apt cache, journal, ~/.cache,
 *  old /tmp files, rotated logs) — user data (G-code, timelapses, configs) is never touched. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchCleanup, runCleanup } from './api'
import { humanSize } from './format'
import HelpNote from './HelpNote.vue'
import type { CleanupResult, CleanupTarget } from './types'

const { t } = useI18n({ useScope: 'global' })

const targets = ref<CleanupTarget[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selected = ref<Set<string>>(new Set())

const busy = ref(false)
const confirm = ref(false)
const result = ref<{ freed: number; details: CleanupResult[] } | null>(null)

async function scan(): Promise<void> {
  loading.value = true
  error.value = null
  result.value = null
  try {
    targets.value = await fetchCleanup()
    // Pre-select every target that's available and would actually free something.
    selected.value = new Set(
      targets.value.filter((tg) => tg.available && tg.bytes > 0).map((tg) => tg.id),
    )
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(scan)

function toggle(id: string): void {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

const selectedBytes = computed(() =>
  targets.value.filter((tg) => selected.value.has(tg.id)).reduce((sum, tg) => sum + tg.bytes, 0),
)

const canClean = computed(() => selected.value.size > 0 && !busy.value)

async function run(): Promise<void> {
  busy.value = true
  error.value = null
  confirm.value = false
  try {
    const res = await runCleanup([...selected.value])
    result.value = { freed: res.freed_bytes, details: res.results }
    await scan() // re-scan so the figures reflect what's left
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="space-y-3">
    <HelpNote topic="cleanup" />

    <div class="flex items-center justify-between gap-2">
      <p class="font-mono text-[11px] opacity-60">{{ t('hostControl.cleanup.subtitle') }}</p>
      <button type="button" class="nb-btn text-xs" :disabled="loading || busy" @click="scan">
        ↻ {{ t('hostControl.cleanup.rescan') }}
      </button>
    </div>

    <p v-if="loading" class="font-mono text-xs opacity-70">
      {{ t('hostControl.cleanup.scanning') }}
    </p>
    <p v-else-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>

    <template v-else>
      <ul class="space-y-1">
        <li
          v-for="tg in targets"
          :key="tg.id"
          class="nb-card flex items-center gap-2 bg-surface p-2"
          :class="{ 'opacity-50': !tg.available }"
        >
          <input
            type="checkbox"
            class="h-4 w-4 shrink-0 accent-ink"
            :checked="selected.has(tg.id)"
            :disabled="!tg.available || tg.bytes === 0 || busy"
            @change="toggle(tg.id)"
          />
          <div class="min-w-0 flex-1">
            <p class="text-xs font-bold">
              {{ t('hostControl.cleanup.targets.' + tg.id + '.label') }}
            </p>
            <p class="text-[11px] leading-snug opacity-60">
              {{ t('hostControl.cleanup.targets.' + tg.id + '.desc') }}
            </p>
          </div>
          <div class="shrink-0 text-end font-mono text-[11px]">
            <p v-if="!tg.available" class="opacity-50">{{ t('hostControl.cleanup.na') }}</p>
            <template v-else>
              <p class="font-bold">{{ humanSize(tg.bytes) }}</p>
              <p v-if="tg.count" class="opacity-50">
                {{ t('hostControl.cleanup.items', { n: tg.count }) }}
              </p>
            </template>
          </div>
        </li>
      </ul>

      <!-- Result of the last run -->
      <p v-if="result" class="nb-card bg-brand-green/10 p-2 font-mono text-xs text-brand-green">
        ✓ {{ t('hostControl.cleanup.freed', { size: humanSize(result.freed) }) }}
      </p>

      <!-- Footer: total + clean button / confirm -->
      <div class="flex flex-wrap items-center gap-2 border-t-2 border-ink pt-2">
        <span class="flex-1 font-mono text-xs">
          {{ t('hostControl.cleanup.selectedTotal', { size: humanSize(selectedBytes) }) }}
        </span>
        <template v-if="!confirm">
          <button
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="!canClean"
            @click="confirm = true"
          >
            🧹 {{ t('hostControl.cleanup.clean') }}
          </button>
        </template>
        <template v-else>
          <span class="text-xs">{{ t('hostControl.cleanup.confirmBody') }}</span>
          <button
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="busy"
            @click="run"
          >
            {{ t('hostControl.cleanup.confirmYes') }}
          </button>
          <button type="button" class="nb-btn text-xs" :disabled="busy" @click="confirm = false">
            {{ t('hostControl.cleanup.cancel') }}
          </button>
        </template>
      </div>
      <p v-if="busy" class="font-mono text-[11px] opacity-60">
        {{ t('hostControl.cleanup.running') }}
      </p>
    </template>
  </div>
</template>
