<script setup lang="ts">
/** Host Control · CAN Bus - view + manage the host's SocketCAN interfaces.
 *
 *  Shows each CAN interface's live link state, controller state, bitrate, bus-error counters and tx
 *  queue length, and lets the user bring it up/down and set its bitrate. Reads are unprivileged;
 *  changes go through the host's passwordless-sudo grant and the backend refuses them while a print
 *  is running (taking the bus down drops every CAN MCU). Bringing a bus down asks for confirmation;
 *  the bitrate can only change while the interface is down (a SocketCAN constraint). */
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import { describeError } from '@/core/describeError'

import { fetchCanBuses, HostActionError, setCanBitrate, setCanLink } from './api'
import type { CanBusStatus } from './types'

const { t } = useI18n({ useScope: 'global' })

const buses = ref<CanBusStatus[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const busy = ref<string | null>(null) // iface currently mutating
const pendingDown = ref<string | null>(null) // iface awaiting "bring down" confirm
const note = ref<string | null>(null)
const actionError = ref<string | null>(null)
const bitrateSel = ref<Record<string, number>>({})

const COMMON_BITRATES = [1000000, 500000, 250000, 125000]
let timer: ReturnType<typeof setInterval> | null = null

async function load(): Promise<void> {
  if (!buses.value.length) loading.value = true
  error.value = null
  try {
    buses.value = await fetchCanBuses()
    for (const b of buses.value) {
      if (bitrateSel.value[b.interface] == null) {
        bitrateSel.value[b.interface] = b.bitrate ?? COMMON_BITRATES[0]
      }
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  timer = setInterval(() => void load(), 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function applyResult(res: { ok: boolean; output: string; needs_setup?: boolean }): void {
  if (res.ok) {
    note.value = t('hostControl.canbus.actionOk')
  } else {
    actionError.value = res.needs_setup
      ? t('hostControl.system.needsSetup')
      : res.output || t('hostControl.canbus.actionFailed')
  }
}

async function doLink(iface: string, up: boolean): Promise<void> {
  busy.value = iface
  note.value = null
  actionError.value = null
  pendingDown.value = null
  try {
    applyResult(await setCanLink(iface, up))
    await load()
  } catch (e) {
    actionError.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

async function doBitrate(iface: string): Promise<void> {
  const bitrate = bitrateSel.value[iface]
  if (!bitrate) return
  busy.value = iface
  note.value = null
  actionError.value = null
  try {
    applyResult(await setCanBitrate(iface, bitrate))
    await load()
  } catch (e) {
    actionError.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

/** CAN controller state → a colour: BUS-OFF is critical, ERROR-PASSIVE is a warning. */
function stateClass(state: string | null): string {
  if (!state) return 'opacity-60'
  const s = state.toUpperCase()
  if (s.includes('BUS-OFF')) return 'text-brand-red font-bold'
  if (s.includes('PASSIVE')) return 'text-brand-yellow font-bold'
  return 'text-brand-lime'
}

function fmtBitrate(b: number | null): string {
  if (b == null) return '-'
  return b % 1000 === 0 ? `${b / 1000} kbit/s` : `${b} bit/s`
}
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('hostControl.canbus.intro') }}</p>
      <button type="button" class="nb-btn text-xs" :disabled="loading" @click="load">
        ↻ {{ t('hostControl.monitor.refresh') }}
      </button>
    </div>

    <p class="rounded-sm bg-brand-yellow/30 p-1.5 text-[11px]">
      ⚠ {{ t('hostControl.canbus.warn') }}
    </p>

    <div
      v-if="error"
      role="alert"
      class="nb-card flex items-start justify-between gap-2 bg-brand-red/10 p-2 font-mono text-xs"
    >
      <span class="min-w-0 wrap-break-word">{{ error }}</span>
      <ReportErrorButton :error="error" />
    </div>

    <p v-if="loading && !buses.length" class="font-mono text-[11px] opacity-60">
      {{ t('hostControl.monitor.loading') }}
    </p>
    <p v-else-if="!buses.length" class="nb-card bg-surface p-3 text-xs opacity-70">
      {{ t('hostControl.canbus.none') }}
    </p>

    <!-- shared action feedback -->
    <p v-if="note" role="status" class="font-mono text-[11px] text-brand-lime">{{ note }}</p>
    <p v-if="actionError" role="alert" class="font-mono text-[11px] text-brand-red">
      {{ actionError }}
    </p>

    <section
      v-for="b in buses"
      :key="b.interface"
      class="nb-card space-y-2 bg-surface p-3"
      dir="ltr"
    >
      <div class="flex items-center justify-between gap-2">
        <h3 class="font-mono text-sm font-bold">{{ b.interface }}</h3>
        <span
          class="rounded-sm border border-ink px-1.5 py-0.5 text-[10px] font-bold"
          :class="
            b.link_up === true
              ? 'bg-brand-lime text-ink'
              : b.link_up === false
                ? 'bg-paper text-ink opacity-70'
                : 'bg-paper opacity-50'
          "
        >
          {{
            b.link_up === true
              ? t('hostControl.canbus.up')
              : b.link_up === false
                ? t('hostControl.canbus.down')
                : t('hostControl.canbus.unknown')
          }}
        </span>
      </div>

      <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
        <dt class="opacity-60">{{ t('hostControl.canbus.controllerState') }}</dt>
        <dd :class="stateClass(b.state)">{{ b.state || '-' }}</dd>
        <dt class="opacity-60">{{ t('hostControl.canbus.driver') }}</dt>
        <dd>{{ b.driver || '-' }}</dd>
        <dt class="opacity-60">{{ t('hostControl.canbus.bitrate') }}</dt>
        <dd class="font-bold">{{ fmtBitrate(b.bitrate) }}</dd>
        <dt class="opacity-60">{{ t('hostControl.canbus.errors') }}</dt>
        <dd>{{ b.errors_rx ?? '-' }} / {{ b.errors_tx ?? '-' }}</dd>
        <dt class="opacity-60">{{ t('hostControl.canbus.txqueue') }}</dt>
        <dd>{{ b.txqueuelen ?? '-' }}</dd>
      </dl>

      <!-- link up/down -->
      <div class="flex flex-wrap items-center gap-2 border-t border-ink/10 pt-2">
        <button
          v-if="b.link_up !== true"
          type="button"
          class="nb-btn bg-paper px-2 py-0.5 text-xs disabled:opacity-50"
          :disabled="busy === b.interface"
          @click="doLink(b.interface, true)"
        >
          {{ t('hostControl.canbus.bringUp') }}
        </button>
        <template v-else>
          <button
            v-if="pendingDown !== b.interface"
            type="button"
            class="nb-btn bg-brand-red/80 px-2 py-0.5 text-xs font-bold text-surface disabled:opacity-50"
            :disabled="busy === b.interface"
            @click="pendingDown = b.interface"
          >
            {{ t('hostControl.canbus.bringDown') }}
          </button>
          <span v-else class="flex items-center gap-2 text-[11px]">
            <span class="text-brand-red">{{ t('hostControl.canbus.confirmDown') }}</span>
            <button
              type="button"
              class="nb-btn bg-brand-red/80 px-1.5 py-0.5 font-bold text-surface"
              :disabled="busy === b.interface"
              @click="doLink(b.interface, false)"
            >
              {{ t('hostControl.canbus.confirm') }}
            </button>
            <button type="button" class="nb-btn bg-paper px-1.5 py-0.5" @click="pendingDown = null">
              {{ t('hostControl.canbus.cancel') }}
            </button>
          </span>
        </template>
      </div>

      <!-- bitrate -->
      <div class="flex flex-wrap items-center gap-2">
        <label class="flex items-center gap-1 text-[11px]">
          <span class="opacity-60">{{ t('hostControl.canbus.bitrate') }}</span>
          <select
            v-model.number="bitrateSel[b.interface]"
            class="nb-input bg-paper px-1 py-0.5"
            :disabled="b.link_up === true || busy === b.interface"
          >
            <option v-for="r in COMMON_BITRATES" :key="r" :value="r">{{ r / 1000 }}k</option>
          </select>
        </label>
        <button
          type="button"
          class="nb-btn bg-paper px-2 py-0.5 text-xs disabled:opacity-50"
          :disabled="b.link_up === true || busy === b.interface"
          @click="doBitrate(b.interface)"
        >
          {{ t('hostControl.canbus.setBitrate') }}
        </button>
        <span v-if="b.link_up === true" class="text-[11px] opacity-60">
          {{ t('hostControl.canbus.downFirst') }}
        </span>
      </div>
    </section>
  </div>
</template>
