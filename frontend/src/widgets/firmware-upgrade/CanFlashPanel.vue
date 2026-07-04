<script setup lang="ts">
/** Guided flash / update for the USB-CAN adapter (a BTT U2C / candleLight dongle) - BETA.
 *
 *  The adapter is NOT a Klipper MCU, so it's flashed over USB-DFU. candleLight / budgetcan firmware
 *  exposes a DFU runtime interface, so the host puts a running adapter into DFU on its own (a
 *  `dfu-util -e` detach) - no button press. We only fall back to the manual BOOT-button entry when
 *  the adapter can't be detached in software. Lives in its own Adapter tab in the Firmware Manager -
 *  the Board Topology widget links here. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchCanRevisions, fetchDfuStatus, flashCanAdapter } from './api'
import type { CanDfuStatus, CanFlashResult, CanFlashRevision } from './types'

const { t } = useI18n({ useScope: 'global' })

const open = ref(true) // its own tab - show expanded by default (still collapsible)
const revs = ref<CanFlashRevision[]>([])
const rev = ref<string>('')
const dfu = ref<CanDfuStatus | null>(null)
const checking = ref(false)
const flashing = ref(false)
const ack = ref(false)
const result = ref<CanFlashResult | null>(null)
const error = ref<string | null>(null)

// Flashable when the adapter is already in DFU, or running and detachable in software.
const flashable = computed(() => !!(dfu.value?.present || dfu.value?.runtime))

onMounted(async () => {
  try {
    revs.value = await fetchCanRevisions()
    rev.value = revs.value[0]?.id ?? ''
  } catch {
    /* leave empty - the section just won't offer revisions */
  }
  void check() // best-effort initial detection so we can enable Flash straight away
})

async function check(): Promise<void> {
  checking.value = true
  error.value = null
  try {
    dfu.value = await fetchDfuStatus()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    checking.value = false
  }
}

async function flash(): Promise<void> {
  if (!rev.value) return
  flashing.value = true
  error.value = null
  result.value = null
  try {
    result.value = await flashCanAdapter(rev.value)
    dfu.value = await fetchDfuStatus().catch(() => dfu.value)
  } catch (e) {
    error.value = describeError(e)
  } finally {
    flashing.value = false
  }
}
</script>

<template>
  <div class="nb-card bg-surface p-2">
    <button
      type="button"
      class="flex w-full items-center justify-between text-sm font-bold"
      @click="open = !open"
    >
      <span class="flex items-center gap-1">
        🔄 {{ t('firmware.canbus.flash.title') }}
        <span
          class="rounded-sm border border-ink bg-brand-yellow px-1 text-[9px] font-bold text-ink"
          >BETA</span
        >
      </span>
      <span aria-hidden="true">{{ open ? '▾' : '▸' }}</span>
    </button>

    <div v-if="open" class="space-y-2 pt-2 text-[11px]">
      <p class="opacity-70">{{ t('firmware.canbus.flash.desc') }}</p>

      <!-- 1. pick the adapter model (wrong firmware can brick it) -->
      <label class="flex items-center gap-1">
        <span class="opacity-60">{{ t('firmware.canbus.flash.revision') }}</span>
        <select v-model="rev" class="nb-input min-w-0 flex-1 bg-paper px-1 py-0.5" dir="ltr">
          <option v-for="r in revs" :key="r.id" :value="r.id">{{ r.label }}</option>
        </select>
      </label>

      <!-- 2. the panel enters DFU on its own - no button press in the common case -->
      <p class="rounded-sm bg-brand-lime/25 p-1">{{ t('firmware.canbus.flash.auto') }}</p>

      <!-- detection status (auto-checked; a manual re-check for after plugging in) -->
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="nb-btn bg-paper px-1.5 py-0.5 disabled:opacity-50"
          :disabled="checking"
          @click="check"
        >
          {{ t('firmware.canbus.flash.check') }}
        </button>
        <span v-if="dfu?.present" class="font-bold text-brand-lime"
          >✓ {{ t('firmware.canbus.flash.ready') }}</span
        >
        <span v-else-if="dfu?.runtime" class="font-bold text-brand-lime"
          >✓ {{ t('firmware.canbus.flash.detected') }}</span
        >
        <span v-else-if="dfu && !dfu.sudo" class="text-brand-red">{{
          t('firmware.canbus.flash.noSudo')
        }}</span>
        <span v-else-if="dfu" class="opacity-70">{{ t('firmware.canbus.flash.notReady') }}</span>
      </div>

      <!-- 3. risk gate + flash (auto-enters DFU; falls back to manual only if that fails) -->
      <label class="flex items-start gap-1">
        <input v-model="ack" type="checkbox" class="mt-0.5" />
        <span>{{ t('firmware.canbus.flash.risk') }}</span>
      </label>
      <button
        type="button"
        class="nb-btn bg-brand-red/80 px-1.5 py-0.5 font-bold text-surface disabled:opacity-40"
        :disabled="!flashable || !ack || flashing"
        @click="flash"
      >
        {{ flashing ? t('firmware.canbus.flash.flashing') : t('firmware.canbus.flash.flash') }}
      </button>

      <!-- manual fallback, only needed if software entry fails -->
      <p class="opacity-60">
        <b>{{ t('firmware.canbus.flash.fallbackLabel') }}</b> {{ t('firmware.canbus.flash.boot') }}
      </p>

      <pre
        v-if="result"
        class="max-h-40 overflow-auto whitespace-pre-wrap rounded-sm bg-paper p-1 text-[10px]"
        :class="result.ok ? '' : 'text-brand-red'"
        dir="ltr"
        >{{ result.output }}</pre>
      <p v-if="error" role="alert" class="text-brand-red">{{ error }}</p>
      <p class="opacity-60">{{ t('firmware.canbus.flash.warn') }}</p>
    </div>
  </div>
</template>
