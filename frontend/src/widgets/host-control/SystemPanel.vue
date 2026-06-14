<script setup lang="ts">
/** Host Control · System — time / locale / hostname / Wi-Fi / power.
 *
 *  Each section reads the current value and applies a change through a guarded backend setter
 *  (validated server-side). Reboot and shutdown ask for an inline confirm and are refused by the
 *  backend while a print is running; changing Wi-Fi warns that it may drop the connection. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import {
  fetchSystemInfo,
  HostActionError,
  power,
  setHostname,
  setKeymap,
  setLocaleLang,
  setNetwork,
  setNtp,
  setTime,
  setTimezone,
  setWifi,
} from './api'
import HelpNote from './HelpNote.vue'
import type { NetworkSetReq, PowerAction, SystemActionResult, SystemInfo } from './types'

const { t } = useI18n({ useScope: 'global' })

const info = ref<SystemInfo | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

// Form state (seeded from info on load / after each apply)
const tz = ref('')
const ntp = ref(true)
const manualTime = ref('')
const lang = ref('')
const keymap = ref('')
const hostname = ref('')
const ssid = ref('')
const wifiPw = ref('')

// Network (IPv4) form state
const netMethod = ref<'auto' | 'manual'>('auto')
const netAddress = ref('')
const netCidr = ref('')
const netGateway = ref('')
const netDns = ref('')
const netConfirm = ref(false)
const netConfirmText = ref('')

const busy = ref<string | null>(null)
const note = ref<string | null>(null)
const actErr = ref<string | null>(null)
const netInfo = ref<string | null>(null) // amber "applying, reconnect" — neither success nor error
const confirmPower = ref<PowerAction | null>(null)

async function reload(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const i = await fetchSystemInfo()
    info.value = i
    tz.value = i.timezone
    ntp.value = i.ntp_enabled
    lang.value = i.lang
    keymap.value = i.keymap
    hostname.value = i.hostname
    const n = i.network
    netMethod.value = n.method === 'manual' ? 'manual' : 'auto'
    netAddress.value = n.address
    netCidr.value = n.cidr != null ? String(n.cidr) : ''
    netGateway.value = n.gateway
    netDns.value = n.dns.join(', ')
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(reload)

/** Map a result onto the green note (ok) or the red error bar (failure / needs-setup). */
function showResult(r: SystemActionResult): void {
  if (r.ok) {
    note.value = r.output || t('hostControl.system.done')
  } else {
    actErr.value = r.needs_setup
      ? t('hostControl.system.needsSetup')
      : r.output || t('hostControl.system.failed')
  }
}

function clearMessages(): void {
  note.value = null
  actErr.value = null
  netInfo.value = null
}

/** Run a setter, surface its message, and re-read system state. */
async function apply(id: string, fn: () => Promise<SystemActionResult>): Promise<void> {
  busy.value = id
  clearMessages()
  try {
    showResult(await fn())
    await reload()
  } catch (e) {
    actErr.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

function onNtpToggle(e: Event): void {
  ntp.value = (e.target as HTMLInputElement).checked
  void apply('ntp', () => setNtp(ntp.value))
}

async function applyWifi(): Promise<void> {
  await apply('wifi', () => setWifi(ssid.value, wifiPw.value))
  wifiPw.value = '' // never keep the password around
}

async function runPower(): Promise<void> {
  if (!confirmPower.value) return
  const action = confirmPower.value
  confirmPower.value = null
  await apply('power', () => power(action))
}

// ── Network (IPv4) ─────────────────────────────────────────────────────────────
const netDevice = computed(() => info.value?.network.device ?? '')

/** Enough filled in to attempt an apply (server re-validates authoritatively). */
const netReady = computed(() => {
  if (netMethod.value === 'auto') return true
  return Boolean(netAddress.value.trim() && netCidr.value.trim() && netGateway.value.trim())
})

/** The typed-confirm must echo the device name shown in the warning. */
const netConfirmReady = computed(
  () => !!netDevice.value && netConfirmText.value.trim() === netDevice.value,
)

/** Will this change likely move/drop the panel's own address (so the socket may die)? Used to tell
 *  an expected self-disconnect (show "reconnect" info) from a genuine fault (show a red error). */
const netChangesReachability = computed(() => {
  const cur = info.value?.network
  if (!cur) return true
  if (netMethod.value === 'auto') return cur.method === 'manual' // static → DHCP moves the IP
  if (cur.method !== 'manual') return true // DHCP → static
  // Both static: only an address/prefix change moves us (a DNS-only edit keeps the link up).
  return netAddress.value.trim() !== cur.address || (Number(netCidr.value) || null) !== cur.cidr
})

function cancelNetwork(): void {
  netConfirm.value = false
  netConfirmText.value = ''
}

async function applyNetwork(): Promise<void> {
  if (!netConfirmReady.value) return // belt-and-suspenders: the lockout confirm must have matched
  const req: NetworkSetReq =
    netMethod.value === 'manual'
      ? {
          method: 'manual',
          address: netAddress.value.trim(),
          cidr: Number(netCidr.value) || null,
          gateway: netGateway.value.trim(),
          dns: netDns.value.trim(),
        }
      : { method: 'auto' }
  const drops = netChangesReachability.value
  busy.value = 'network'
  clearMessages()
  netConfirm.value = false
  netConfirmText.value = ''
  try {
    const r = await setNetwork(req)
    if (!r.ok) {
      actErr.value = r.needs_setup
        ? t('hostControl.system.needsSetup')
        : r.output || t('hostControl.system.failed')
    } else if (drops) {
      // The response came back but `nmcli connection up` may still drop our IP a moment later —
      // don't reload() over a link that's about to die (it would hang). Tell the user to reconnect.
      netInfo.value = t('hostControl.system.network.applyingReconnect')
    } else {
      note.value = r.output || t('hostControl.system.done')
      await reload() // safe: a DNS-only change keeps the connection up
    }
  } catch (e) {
    // A real HTTP error (400/403) is a backend rejection — always show it red. Any other failure
    // (the fetch never completing) means no response: if this change was going to drop our own
    // connection, that's the expected self-disconnect → "reconnect" info; otherwise nothing applied
    // (backend down/unreachable) → a genuine red error.
    if (e instanceof HostActionError) {
      actErr.value = e.message
    } else if (drops) {
      netInfo.value = t('hostControl.system.network.applyingReconnect')
    } else {
      actErr.value = describeError(e)
    }
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="space-y-3">
    <HelpNote topic="system" />

    <p v-if="loading" class="font-mono text-xs opacity-70">
      {{ t('hostControl.system.loading') }}
    </p>
    <p v-else-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>

    <template v-else-if="info">
      <!-- Shared result/error bar -->
      <p v-if="note" class="nb-card bg-brand-green/10 p-2 font-mono text-[11px] text-brand-green">
        ✓ {{ note }}
      </p>
      <p v-if="netInfo" role="status" class="nb-card bg-brand-yellow/15 p-2 font-mono text-[11px]">
        ⟳ {{ netInfo }}
      </p>
      <p v-if="actErr" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">
        {{ actErr }}
      </p>

      <!-- Time & Date -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.timeTitle') }}
        </h3>
        <label class="flex cursor-pointer items-center gap-2 text-xs">
          <input
            type="checkbox"
            class="h-4 w-4 accent-ink"
            :checked="ntp"
            :disabled="busy === 'ntp'"
            @change="onNtpToggle"
          />
          {{ t('hostControl.system.ntp') }}
        </label>
        <div class="flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.timezone')
            }}</span>
            <select
              v-model="tz"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
            >
              <option v-for="z in info.timezones" :key="z" :value="z">{{ z }}</option>
            </select>
          </label>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'tz' || tz === info.timezone"
            @click="apply('tz', () => setTimezone(tz))"
          >
            {{ t('hostControl.system.apply') }}
          </button>
        </div>
        <div class="flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.manualTime')
            }}</span>
            <input
              v-model="manualTime"
              type="text"
              placeholder="2026-06-14 12:00:00"
              :disabled="ntp"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs disabled:opacity-40"
            />
          </label>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'time' || ntp || !manualTime"
            @click="apply('time', () => setTime(manualTime))"
          >
            {{ t('hostControl.system.apply') }}
          </button>
        </div>
        <p v-if="ntp" class="text-[11px] opacity-60">
          {{ t('hostControl.system.manualTimeHint') }}
        </p>
      </section>

      <!-- Language & Keyboard -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.localeTitle') }}
        </h3>
        <div class="flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.language')
            }}</span>
            <select
              v-model="lang"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
            >
              <option v-for="l in info.locales" :key="l" :value="l">{{ l }}</option>
            </select>
          </label>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'lang' || lang === info.lang"
            @click="apply('lang', () => setLocaleLang(lang))"
          >
            {{ t('hostControl.system.apply') }}
          </button>
        </div>
        <div v-if="info.keymaps.length" class="flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.keymap')
            }}</span>
            <select
              v-model="keymap"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
            >
              <option v-for="k in info.keymaps" :key="k" :value="k">{{ k }}</option>
            </select>
          </label>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'keymap' || keymap === info.keymap"
            @click="apply('keymap', () => setKeymap(keymap))"
          >
            {{ t('hostControl.system.apply') }}
          </button>
        </div>
      </section>

      <!-- Hostname -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.hostnameTitle') }}
        </h3>
        <div class="flex flex-wrap items-end gap-2">
          <input
            v-model="hostname"
            type="text"
            class="min-w-0 flex-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
          />
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'hostname' || !hostname || hostname === info.hostname"
            @click="apply('hostname', () => setHostname(hostname))"
          >
            {{ t('hostControl.system.apply') }}
          </button>
        </div>
        <p class="text-[11px] opacity-60">{{ t('hostControl.system.hostnameHint') }}</p>
      </section>

      <!-- Network (IPv4) -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.network.title') }}
        </h3>
        <HelpNote topic="network" />
        <p v-if="!info.network.configurable" class="text-[11px] opacity-60">
          {{ t('hostControl.system.network.unavailable') }}
        </p>
        <template v-else>
          <!-- Current config summary -->
          <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
            <dt class="opacity-60">{{ t('hostControl.system.network.device') }}</dt>
            <dd class="font-bold">{{ info.network.device }} ({{ info.network.connection }})</dd>
            <dt class="opacity-60">{{ t('hostControl.system.network.method') }}</dt>
            <dd>
              {{
                info.network.method === 'manual'
                  ? t('hostControl.system.network.manual')
                  : t('hostControl.system.network.auto')
              }}
            </dd>
            <dt class="opacity-60">{{ t('hostControl.system.network.address') }}</dt>
            <dd>
              {{ info.network.address || '—'
              }}{{ info.network.cidr != null ? '/' + info.network.cidr : '' }}
            </dd>
            <dt class="opacity-60">{{ t('hostControl.system.network.gateway') }}</dt>
            <dd>{{ info.network.gateway || '—' }}</dd>
            <dt class="opacity-60">{{ t('hostControl.system.network.dns') }}</dt>
            <dd>{{ info.network.dns.length ? info.network.dns.join(', ') : '—' }}</dd>
          </dl>

          <!-- DHCP / Static toggle -->
          <div class="inline-flex overflow-hidden rounded-brutal border-2 border-ink" role="group">
            <button
              v-for="m in ['auto', 'manual'] as const"
              :key="m"
              type="button"
              class="nb-seg whitespace-nowrap text-[11px]"
              :class="
                netMethod === m ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'
              "
              :aria-pressed="netMethod === m"
              @click="netMethod = m"
            >
              {{ t('hostControl.system.network.' + m) }}
            </button>
          </div>

          <!-- Static fields -->
          <div v-if="netMethod === 'manual'" class="space-y-2">
            <div class="flex flex-wrap items-end gap-2">
              <label class="min-w-0 flex-1">
                <span class="mb-0.5 block text-[11px] opacity-60">{{
                  t('hostControl.system.network.address')
                }}</span>
                <input
                  v-model="netAddress"
                  type="text"
                  placeholder="192.168.0.50"
                  class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
                />
              </label>
              <label class="w-24">
                <span class="mb-0.5 block text-[11px] opacity-60">{{
                  t('hostControl.system.network.cidr')
                }}</span>
                <input
                  v-model="netCidr"
                  type="number"
                  min="1"
                  max="30"
                  placeholder="24"
                  class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
                />
              </label>
            </div>
            <label class="block">
              <span class="mb-0.5 block text-[11px] opacity-60">{{
                t('hostControl.system.network.gateway')
              }}</span>
              <input
                v-model="netGateway"
                type="text"
                placeholder="192.168.0.1"
                class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
              />
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[11px] opacity-60">{{
                t('hostControl.system.network.dns')
              }}</span>
              <input
                v-model="netDns"
                type="text"
                placeholder="1.1.1.1, 8.8.8.8"
                class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
              />
              <span class="mt-0.5 block text-[11px] opacity-50">{{
                t('hostControl.system.network.dnsHint')
              }}</span>
            </label>
          </div>

          <p class="text-[11px] text-brand-red">⚠ {{ t('hostControl.system.network.warning') }}</p>

          <!-- Apply + typed-confirm -->
          <button
            v-if="!netConfirm"
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="busy === 'network' || !netReady"
            @click="netConfirm = true"
          >
            {{ t('hostControl.system.network.apply') }}
          </button>
          <div v-else class="nb-card space-y-1.5 bg-brand-red/10 p-2" role="alertdialog">
            <p class="text-xs">
              {{ t('hostControl.system.network.confirmPrompt', { device: netDevice }) }}
            </p>
            <input
              v-model="netConfirmText"
              type="text"
              :placeholder="netDevice"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
            />
            <div class="flex gap-1">
              <button
                type="button"
                class="nb-btn border-brand-red text-[11px] text-brand-red"
                :disabled="busy === 'network' || !netConfirmReady"
                @click="applyNetwork"
              >
                {{ t('hostControl.system.network.confirmYes') }}
              </button>
              <button
                type="button"
                class="nb-btn text-[11px]"
                :disabled="busy === 'network'"
                @click="cancelNetwork"
              >
                {{ t('hostControl.system.cancel') }}
              </button>
            </div>
          </div>
        </template>
      </section>

      <!-- Wi-Fi -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.wifiTitle') }}
        </h3>
        <p v-if="!info.wifi_available" class="text-[11px] opacity-60">
          {{ t('hostControl.system.wifiUnavailable') }}
        </p>
        <template v-else>
          <p class="text-[11px] text-brand-red">⚠ {{ t('hostControl.system.wifiWarning') }}</p>
          <label class="block">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.ssid')
            }}</span>
            <input
              v-model="ssid"
              type="text"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
            />
          </label>
          <label class="block">
            <span class="mb-0.5 block text-[11px] opacity-60">{{
              t('hostControl.system.password')
            }}</span>
            <input
              v-model="wifiPw"
              type="password"
              autocomplete="off"
              class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-xs"
            />
          </label>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'wifi' || !ssid"
            @click="applyWifi"
          >
            {{ t('hostControl.system.connect') }}
          </button>
        </template>
      </section>

      <!-- Power -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('hostControl.system.powerTitle') }}
        </h3>
        <p class="text-[11px] opacity-60">{{ t('hostControl.system.powerWarning') }}</p>
        <div v-if="!confirmPower" class="flex gap-2">
          <button
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="busy === 'power'"
            @click="confirmPower = 'reboot'"
          >
            ⟳ {{ t('hostControl.system.reboot') }}
          </button>
          <button
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="busy === 'power'"
            @click="confirmPower = 'shutdown'"
          >
            ⏻ {{ t('hostControl.system.shutdown') }}
          </button>
        </div>
        <div
          v-else
          class="nb-card flex flex-wrap items-center gap-2 bg-brand-red/10 p-2"
          role="alertdialog"
        >
          <span class="flex-1 text-xs">
            {{
              confirmPower === 'reboot'
                ? t('hostControl.system.confirmReboot')
                : t('hostControl.system.confirmShutdown')
            }}
          </span>
          <button
            type="button"
            class="nb-btn border-brand-red text-xs text-brand-red"
            :disabled="busy === 'power'"
            @click="runPower"
          >
            {{ t('hostControl.system.confirmYes') }}
          </button>
          <button
            type="button"
            class="nb-btn text-xs"
            :disabled="busy === 'power'"
            @click="confirmPower = null"
          >
            {{ t('hostControl.system.cancel') }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
