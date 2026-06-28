<script setup lang="ts">
/** Guided flash / update for the USB-CAN adapter (a BTT U2C / candleLight dongle). The adapter is
 *  NOT a Klipper MCU, so it's flashed over USB-DFU: the user must HOLD the BOOT button while
 *  plugging the cable in (gs_usb has no software bootloader-entry), then the host runs dfu-util.
 *  This walks that with the button timing front and centre + a DFU check before Flash is enabled. */
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchCanRevisions, fetchDfuStatus, flashCanAdapter } from './api'
import type { CanDfuStatus, CanFlashResult, CanFlashRevision, TopologyCanBus } from './types'

const props = defineProps<{ canBus: TopologyCanBus; busy: boolean }>()

const { t } = useI18n({ useScope: 'global' })

const open = ref(false)
const revs = ref<CanFlashRevision[]>([])
const rev = ref<string>('')
const dfu = ref<CanDfuStatus | null>(null)
const checking = ref(false)
const flashing = ref(false)
const ack = ref(false)
const result = ref<CanFlashResult | null>(null)
const error = ref<string | null>(null)

/** Default the picker to the confirmed board's family (u2c-v1 vs u2c-v2), else the first revision. */
function defaultRev(): string {
  const id = props.canBus.board_id ?? ''
  if (id.includes('v1')) return 'u2c-v1'
  if (id.includes('v2')) return 'u2c-v2'
  return revs.value[0]?.id ?? ''
}

onMounted(async () => {
  try {
    revs.value = await fetchCanRevisions()
    rev.value = defaultRev()
  } catch {
    /* leave empty - the section just won't offer revisions */
  }
})

// A different adapter selected -> reset the flow.
watch(
  () => props.canBus.interface,
  () => {
    dfu.value = null
    result.value = null
    error.value = null
    ack.value = false
  },
)

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
  <div class="border-t border-ink/15 pt-1">
    <button
      type="button"
      class="flex w-full items-center justify-between text-[11px] font-bold"
      @click="open = !open"
    >
      <span>🔄 {{ t('boardTopology.canbus.flash.title') }}</span>
      <span aria-hidden="true">{{ open ? '▾' : '▸' }}</span>
    </button>

    <div v-if="open" class="space-y-2 pt-1 text-[11px]">
      <p class="opacity-70">{{ t('boardTopology.canbus.flash.desc') }}</p>

      <!-- 1. pick the adapter model (wrong firmware can brick it) -->
      <label class="flex items-center gap-1">
        <span class="opacity-60">{{ t('boardTopology.canbus.flash.revision') }}</span>
        <select v-model="rev" class="nb-input min-w-0 flex-1 bg-paper px-1 py-0.5" dir="ltr">
          <option v-for="r in revs" :key="r.id" :value="r.id">{{ r.label }}</option>
        </select>
      </label>

      <!-- 2. the BOOT-button timing (the crux of the guided flow) -->
      <p class="rounded-sm bg-brand-yellow/30 p-1">
        <b>1.</b> {{ t('boardTopology.canbus.flash.boot') }}
      </p>

      <!-- 3. confirm it actually entered DFU before enabling Flash -->
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="nb-btn bg-paper px-1.5 py-0.5 disabled:opacity-50"
          :disabled="checking"
          @click="check"
        >
          <b>2.</b> {{ t('boardTopology.canbus.flash.check') }}
        </button>
        <span v-if="dfu?.present" class="font-bold text-brand-lime"
          >✓ {{ t('boardTopology.canbus.flash.ready') }}</span
        >
        <span v-else-if="dfu && !dfu.sudo" class="text-brand-red">{{
          t('boardTopology.canbus.flash.noSudo')
        }}</span>
        <span v-else-if="dfu" class="opacity-70">{{
          t('boardTopology.canbus.flash.notReady')
        }}</span>
      </div>

      <!-- 4. risk gate + flash -->
      <label class="flex items-start gap-1">
        <input v-model="ack" type="checkbox" class="mt-0.5" />
        <span>{{ t('boardTopology.canbus.flash.risk') }}</span>
      </label>
      <button
        type="button"
        class="nb-btn bg-brand-red/80 px-1.5 py-0.5 font-bold text-surface disabled:opacity-40"
        :disabled="!dfu?.present || !ack || flashing || busy"
        @click="flash"
      >
        <b>3.</b>
        {{
          flashing
            ? t('boardTopology.canbus.flash.flashing')
            : t('boardTopology.canbus.flash.flash')
        }}
      </button>

      <pre
        v-if="result"
        class="max-h-40 overflow-auto whitespace-pre-wrap rounded-sm bg-paper p-1 text-[10px]"
        :class="result.ok ? '' : 'text-brand-red'"
        dir="ltr"
        >{{ result.output }}</pre
      >
      <p v-if="error" role="alert" class="text-brand-red">{{ error }}</p>
      <p class="opacity-60">{{ t('boardTopology.canbus.flash.warn') }}</p>
    </div>
  </div>
</template>
