<script setup lang="ts">
/** Host Control · CAN Bus - view + manage the host's SocketCAN interfaces.
 *
 *  Shows each CAN interface's live link state, controller state, bitrate, bus-error counters and tx
 *  queue length, and lets the user bring it up/down, set its bitrate and edit advanced parameters.
 *  Reads are unprivileged; changes go through the host's passwordless-sudo grant and the backend
 *  refuses them while a print is running (taking the bus down drops every CAN MCU). Applying a
 *  bitrate/parameter change runs the whole cycle for the user - down (if up) → apply → up → Klipper
 *  FIRMWARE_RESTART so the CAN MCUs reconnect - behind a confirmation (it briefly drops the bus). */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'
import { describeError } from '@/core/describeError'

import {
  fetchCanBuses,
  HostActionError,
  restartCanBus,
  restartKlipper,
  setCanBitrate,
  setCanLink,
  setCanParams,
} from './api'
import type { CanBusActionResult, CanBusStatus } from './types'

const { t } = useI18n({ useScope: 'global' })

const buses = ref<CanBusStatus[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const busy = ref<string | null>(null) // iface currently mutating
const pendingDown = ref<string | null>(null) // iface awaiting "bring down" confirm
const note = ref<string | null>(null)
const actionError = ref<string | null>(null)
const bitrateSel = ref<Record<string, number>>({})

// A change that needs the bus down (bitrate / advanced params) or a Klipper restart is confirmed
// first - it briefly drops every CAN MCU and restarts Klipper, so never do it mid-print.
type ConfirmKind = 'bitrate' | 'params' | 'klipper'
const confirmAction = ref<{ iface: string; kind: ConfirmKind } | null>(null)
const confirmMsgKey: Record<ConfirmKind, string> = {
  bitrate: 'hostControl.canbus.confirmBitrate',
  params: 'hostControl.canbus.confirmParams',
  klipper: 'hostControl.canbus.confirmKlipper',
}
const confirmMsg = computed(() =>
  confirmAction.value ? t(confirmMsgKey[confirmAction.value.kind]) : '',
)
function askConfirm(iface: string, kind: ConfirmKind): void {
  note.value = null
  actionError.value = null
  pendingDown.value = null
  confirmAction.value = { iface, kind }
}
/** Open the bring-down confirm, closing any open bitrate/params/klipper confirm first (so the two
 *  confirmation prompts are mutually exclusive). */
function askBringDown(iface: string): void {
  confirmAction.value = null
  pendingDown.value = iface
}
async function runConfirmed(): Promise<void> {
  const a = confirmAction.value
  if (!a) return
  confirmAction.value = null
  if (a.kind === 'klipper') return doRestartKlipper(a.iface)
  const b = buses.value.find((x) => x.interface === a.iface)
  if (!b) return
  if (a.kind === 'bitrate') return doBitrate(a.iface)
  return applyParams(b)
}

const COMMON_BITRATES = [1000000, 500000, 250000, 125000]
let timer: ReturnType<typeof setInterval> | null = null

// -- Advanced per-interface parameter editor -----------------------------------
/** Control-mode flags shown as checkboxes (api key → i18n label key). */
const FLAG_KEYS = [
  'listen_only',
  'loopback',
  'triple_sampling',
  'one_shot',
  'berr_reporting',
] as const
type FlagKey = (typeof FLAG_KEYS)[number]

interface EditState {
  sample_point: string
  sjw: string
  restart_ms: string
  txqueuelen: string
  fd: boolean
  dbitrate: string
  dsample_point: string
  flags: Record<FlagKey, boolean>
}

const advancedOpen = ref<Record<string, boolean>>({})
const edit = ref<Record<string, EditState>>({})

/** Seed the editor for an interface from its live params (called when the panel is opened). */
function seedEdit(b: CanBusStatus): void {
  const p = b.params ?? {}
  const f = p.flags ?? {}
  edit.value[b.interface] = {
    sample_point: p.sample_point != null ? String(p.sample_point) : '',
    sjw: p.sjw != null ? String(p.sjw) : '',
    restart_ms: p.restart_ms != null ? String(p.restart_ms) : '',
    txqueuelen: b.txqueuelen != null ? String(b.txqueuelen) : '',
    fd: !!f.fd,
    dbitrate: p.dbitrate != null ? String(p.dbitrate) : '',
    dsample_point: p.dsample_point != null ? String(p.dsample_point) : '',
    flags: Object.fromEntries(FLAG_KEYS.map((k) => [k, !!f[k]])) as Record<FlagKey, boolean>,
  }
}

function toggleAdvanced(b: CanBusStatus): void {
  const open = !advancedOpen.value[b.interface]
  advancedOpen.value[b.interface] = open
  if (open) seedEdit(b)
}

function isBusOff(b: CanBusStatus): boolean {
  return (b.state ?? '').toUpperCase().includes('BUS-OFF')
}

const numOrNull = (s: string): number | null => {
  const n = Number(s)
  return s.trim() !== '' && !Number.isNaN(n) ? n : null
}

async function applyParams(b: CanBusStatus): Promise<void> {
  const e = edit.value[b.interface]
  if (!e) return
  const params: Record<string, number | boolean> = {}
  for (const [key, raw] of [
    ['sample_point', e.sample_point],
    ['sjw', e.sjw],
    ['restart_ms', e.restart_ms],
    ['txqueuelen', e.txqueuelen],
  ] as const) {
    const n = numOrNull(raw)
    if (n != null) params[key] = n
  }
  for (const k of FLAG_KEYS) params[k] = e.flags[k]
  if (b.limits?.fd_supported) {
    params.fd = e.fd
    if (e.fd) {
      const db = numOrNull(e.dbitrate)
      const dsp = numOrNull(e.dsample_point)
      if (db != null) params.dbitrate = db
      if (dsp != null) params.dsample_point = dsp
    }
  }
  busy.value = b.interface
  note.value = null
  actionError.value = null
  try {
    // restart=true: the backend cycles the bus down→apply→up, then FIRMWARE_RESTARTs Klipper so the
    // CAN MCUs reconnect with the new settings (otherwise the change never reaches the printer).
    applyResult(
      await setCanParams(b.interface, params, true),
      t('hostControl.canbus.appliedRestarting'),
    )
    await load()
  } catch (err) {
    actionError.value = err instanceof HostActionError ? err.message : describeError(err)
  } finally {
    busy.value = null
  }
}

async function doRestart(iface: string): Promise<void> {
  busy.value = iface
  note.value = null
  actionError.value = null
  try {
    applyResult(await restartCanBus(iface))
    await load()
  } catch (err) {
    actionError.value = err instanceof HostActionError ? err.message : describeError(err)
  } finally {
    busy.value = null
  }
}

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

function applyResult(res: CanBusActionResult, successMsg?: string): void {
  if (!res.ok) {
    actionError.value = res.needs_setup
      ? t('hostControl.system.needsSetup')
      : res.output || t('hostControl.canbus.actionFailed')
    return
  }
  // The ip change succeeded; surface a follow-up Klipper-restart failure rather than a false "OK".
  if (res.restarted === false) {
    actionError.value = res.output || t('hostControl.canbus.restartFailed')
    return
  }
  note.value = successMsg ?? t('hostControl.canbus.actionOk')
}

async function doRestartKlipper(iface: string): Promise<void> {
  busy.value = iface
  note.value = null
  actionError.value = null
  try {
    applyResult(await restartKlipper(), t('hostControl.canbus.restartingKlipper'))
    await load()
  } catch (err) {
    actionError.value = err instanceof HostActionError ? err.message : describeError(err)
  } finally {
    busy.value = null
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
    applyResult(
      await setCanBitrate(iface, bitrate, true),
      t('hostControl.canbus.appliedRestarting'),
    )
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
            @click="askBringDown(b.interface)"
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
        <!-- Restart Klipper + every MCU so the CAN MCUs reconnect after a manual bus change. -->
        <button
          type="button"
          class="nb-btn bg-paper px-2 py-0.5 text-xs disabled:opacity-50"
          :disabled="busy === b.interface"
          @click="askConfirm(b.interface, 'klipper')"
        >
          {{ t('hostControl.canbus.restartKlipper') }}
        </button>
      </div>

      <!-- shared confirmation: bitrate / advanced params / Klipper restart all drop the bus briefly -->
      <div
        v-if="confirmAction && confirmAction.iface === b.interface"
        class="nb-card space-y-2 bg-brand-yellow/20 p-2 text-[11px]"
      >
        <p class="font-bold">⚠ {{ confirmMsg }}</p>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="nb-btn bg-brand-red/80 px-2 py-0.5 font-bold text-surface disabled:opacity-50"
            :disabled="busy === b.interface"
            @click="runConfirmed"
          >
            {{ t('hostControl.canbus.confirm') }}
          </button>
          <button type="button" class="nb-btn bg-paper px-2 py-0.5" @click="confirmAction = null">
            {{ t('hostControl.canbus.cancel') }}
          </button>
        </div>
      </div>

      <!-- bitrate -->
      <div class="flex flex-wrap items-center gap-2">
        <label class="flex items-center gap-1 text-[11px]">
          <span class="opacity-60">{{ t('hostControl.canbus.bitrate') }}</span>
          <select
            v-model.number="bitrateSel[b.interface]"
            class="nb-input bg-paper px-1 py-0.5"
            :disabled="busy === b.interface"
          >
            <option v-for="r in COMMON_BITRATES" :key="r" :value="r">{{ r / 1000 }}k</option>
          </select>
        </label>
        <button
          type="button"
          class="nb-btn bg-paper px-2 py-0.5 text-xs disabled:opacity-50"
          :disabled="busy === b.interface"
          @click="askConfirm(b.interface, 'bitrate')"
        >
          {{ t('hostControl.canbus.setBitrate') }}
        </button>
      </div>

      <!-- restart a BUS-OFF controller -->
      <div v-if="isBusOff(b)" class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="nb-btn bg-brand-yellow px-2 py-0.5 text-xs font-bold disabled:opacity-50"
          :disabled="busy === b.interface"
          @click="doRestart(b.interface)"
        >
          {{ t('hostControl.canbus.restart') }}
        </button>
        <span class="text-[11px] opacity-60">{{ t('hostControl.canbus.restartHint') }}</span>
      </div>

      <!-- advanced parameters (bit timing / robustness / control modes / CAN-FD / tx queue) -->
      <div class="border-t border-ink/10 pt-2">
        <button type="button" class="text-[11px] font-bold opacity-80" @click="toggleAdvanced(b)">
          {{ advancedOpen[b.interface] ? '▾' : '▸' }} {{ t('hostControl.canbus.advanced') }}
        </button>
        <div v-if="advancedOpen[b.interface] && edit[b.interface]" class="space-y-2 pt-2">
          <p class="text-[11px] opacity-60">{{ t('hostControl.canbus.noiseHint') }}</p>
          <p class="block text-[11px] text-brand-yellow">{{ t('hostControl.canbus.applyHint') }}</p>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <label class="flex flex-col gap-0.5">
              <span class="opacity-60">{{ t('hostControl.canbus.samplePoint') }}</span>
              <input
                v-model="edit[b.interface].sample_point"
                type="number"
                step="0.001"
                min="0"
                max="0.999"
                class="nb-input bg-paper px-1 py-0.5"
                :disabled="busy === b.interface"
              />
            </label>
            <label class="flex flex-col gap-0.5">
              <span class="opacity-60"
                >{{ t('hostControl.canbus.sjw')
                }}<template v-if="b.limits?.sjw_max"> (≤{{ b.limits.sjw_max }})</template></span
              >
              <input
                v-model="edit[b.interface].sjw"
                type="number"
                min="1"
                :max="b.limits?.sjw_max ?? 128"
                class="nb-input bg-paper px-1 py-0.5"
                :disabled="busy === b.interface"
              />
            </label>
            <label class="flex flex-col gap-0.5">
              <span class="opacity-60">{{ t('hostControl.canbus.restartMs') }}</span>
              <input
                v-model="edit[b.interface].restart_ms"
                type="number"
                min="0"
                class="nb-input bg-paper px-1 py-0.5"
                :disabled="busy === b.interface"
              />
            </label>
            <label class="flex flex-col gap-0.5">
              <span class="opacity-60">{{ t('hostControl.canbus.txQueueLen') }}</span>
              <input
                v-model="edit[b.interface].txqueuelen"
                type="number"
                min="0"
                class="nb-input bg-paper px-1 py-0.5"
                :disabled="busy === b.interface"
              />
            </label>
          </div>

          <!-- control-mode flags -->
          <div class="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
            <label v-for="fk in FLAG_KEYS" :key="fk" class="flex items-center gap-1">
              <input
                v-model="edit[b.interface].flags[fk]"
                type="checkbox"
                :disabled="busy === b.interface"
              />
              {{ t('hostControl.canbus.flag.' + fk) }}
            </label>
          </div>

          <!-- CAN-FD (only when the controller supports it) -->
          <div v-if="b.limits?.fd_supported" class="space-y-1 border-t border-ink/10 pt-1">
            <label class="flex items-center gap-1 text-[11px] font-bold">
              <input
                v-model="edit[b.interface].fd"
                type="checkbox"
                :disabled="busy === b.interface"
              />
              {{ t('hostControl.canbus.fd') }}
            </label>
            <div v-if="edit[b.interface].fd" class="grid grid-cols-2 gap-2 text-[11px]">
              <label class="flex flex-col gap-0.5">
                <span class="opacity-60">{{ t('hostControl.canbus.dbitrate') }}</span>
                <input
                  v-model="edit[b.interface].dbitrate"
                  type="number"
                  class="nb-input bg-paper px-1 py-0.5"
                  :disabled="busy === b.interface"
                />
              </label>
              <label class="flex flex-col gap-0.5">
                <span class="opacity-60">{{ t('hostControl.canbus.dsamplePoint') }}</span>
                <input
                  v-model="edit[b.interface].dsample_point"
                  type="number"
                  step="0.001"
                  class="nb-input bg-paper px-1 py-0.5"
                  :disabled="busy === b.interface"
                />
              </label>
            </div>
          </div>

          <button
            type="button"
            class="nb-btn bg-paper px-2 py-0.5 text-xs disabled:opacity-50"
            :disabled="busy === b.interface"
            @click="askConfirm(b.interface, 'params')"
          >
            {{ t('hostControl.canbus.applyParams') }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>
