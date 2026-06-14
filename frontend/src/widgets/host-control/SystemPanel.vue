<script setup lang="ts">
/** Host Control · System — time / locale / hostname / Wi-Fi / power.
 *
 *  Each section reads the current value and applies a change through a guarded backend setter
 *  (validated server-side). Reboot and shutdown ask for an inline confirm and are refused by the
 *  backend while a print is running; changing Wi-Fi warns that it may drop the connection. */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import {
  fetchSystemInfo,
  HostActionError,
  power,
  setHostname,
  setKeymap,
  setLocaleLang,
  setNtp,
  setTime,
  setTimezone,
  setWifi,
} from './api'
import HelpNote from './HelpNote.vue'
import type { PowerAction, SystemActionResult, SystemInfo } from './types'

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

const busy = ref<string | null>(null)
const note = ref<string | null>(null)
const actErr = ref<string | null>(null)
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
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(reload)

/** Run a setter, surface its message, and re-read system state. */
async function apply(id: string, fn: () => Promise<SystemActionResult>): Promise<void> {
  busy.value = id
  note.value = null
  actErr.value = null
  try {
    const r = await fn()
    note.value = r.output || t('hostControl.system.done')
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
