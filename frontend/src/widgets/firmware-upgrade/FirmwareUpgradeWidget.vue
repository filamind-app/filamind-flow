<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import LogPane from '@/components/ui/LogPane.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import ExternalFirmwarePanel from './ExternalFirmwarePanel.vue'
import FirmwareConfigEditor from './FirmwareConfigEditor.vue'
import FirmwareGuided from './FirmwareGuided.vue'
import FirmwareDevicesPanel from './FirmwareDevicesPanel.vue'
import FirmwareFlashConfirm from './FirmwareFlashConfirm.vue'
import HelpNote from './HelpNote.vue'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import {
  buildFirmware,
  cancelTask,
  fetchBeacon,
  fetchBoards,
  fetchDevices,
  fetchFirmwareStatus,
  fetchHealth,
  fetchProfiles,
  fetchServices,
  fetchTask,
  flashBeacon,
  flashBoard,
  manageServices,
  rebootBoard,
  startBatch,
} from './api'
import type {
  BeaconResponse,
  Board,
  Device,
  FirmwareProfile,
  FirmwareStatus,
  FirmwareTools,
  FlashIntent,
  FlashRequest,
  HealthReport,
  ServiceInfo,
} from './types'

const { t } = useI18n({ useScope: 'global' })

type FwMode = 'guided' | 'status' | 'configure' | 'devices' | 'external'
const mode = ref<FwMode>('status')
const FW_TABS = computed<{ id: FwMode; label: string }[]>(() => [
  { id: 'guided', label: t('firmware.widget.tabGuided') },
  { id: 'status', label: t('firmware.widget.tabStatus') },
  { id: 'configure', label: t('firmware.widget.tabConfigure') },
  { id: 'devices', label: t('firmware.widget.tabDevices') },
  { id: 'external', label: t('firmware.widget.tabExternal') },
])
const status = ref<FirmwareStatus | null>(null)
const boards = ref<Board[]>([])
const devices = ref<Device[]>([])
const profiles = ref<FirmwareProfile[]>([])
const services = ref<ServiceInfo[]>([])
const servicesBusy = ref(false)
const beacon = ref<BeaconResponse | null>(null)
const beaconLog = ref('')
const beaconFlashing = ref(false)
const health = ref<HealthReport | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

const healthIssues = computed(() => health.value?.checks.filter((c) => !c.ok) ?? [])
const healthTitle = computed(() =>
  healthIssues.value.map((c) => `${c.name}: ${c.detail}`).join('\n'),
)

/** Live bus mode (service / ready / dfu / …) keyed by board id. */
const liveMode = computed(() => {
  const map: Record<string, string> = {}
  for (const b of boards.value) map[b.id] = b.mode
  return map
})

/** Devices ready to operate here: only those added AND given a profile. */
const operationalDevices = computed(() => devices.value.filter((d) => d.profile))
/** Live counts that drive the Guided checklist (#118). */
const builtProfileCount = computed(() => profiles.value.filter((p) => p.built).length)
const outdatedCount = computed(() => operationalDevices.value.filter(isOutdated).length)

function boardModeClass(mode: string): string {
  if (mode === 'service') return 'bg-brand-lime'
  if (mode === 'ready' || mode === 'dfu') return 'bg-brand-yellow'
  return 'bg-surface opacity-70'
}

const TOOLS: { key: keyof FirmwareTools; label: string }[] = [
  { key: 'klipper', label: 'Klipper' },
  { key: 'katapult', label: 'Katapult' },
  { key: 'flashtool', label: 'flashtool' },
  { key: 'dfu_util', label: 'dfu-util' },
  { key: 'avrdude', label: 'avrdude' },
  { key: 'can_utils', label: 'can-utils' },
]

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const [statusData, boardsData, devicesData, profilesData] = await Promise.all([
      fetchFirmwareStatus(),
      fetchBoards(),
      fetchDevices(),
      fetchProfiles(),
    ])
    status.value = statusData
    boards.value = boardsData.boards
    devices.value = devicesData.devices
    profiles.value = profilesData.profiles
    error.value = null
  } catch (e) {
    // Surface the failure on silent refreshes too. Otherwise a poll that fails after
    // the first successful load clears nothing and leaves the widget blank.
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
  try {
    services.value = (await fetchServices()).services
  } catch {
    /* services are optional context — ignore */
  }
  try {
    beacon.value = await fetchBeacon()
  } catch {
    /* beacon probes are optional — ignore */
  }
  try {
    health.value = await fetchHealth()
  } catch {
    /* health is optional context — ignore */
  }
}

// --- Operations on the registered devices: batch + per-device build / flash / reboot ---
const BATCH_ACTIONS = computed(() => [
  { action: 'build-all', label: t('firmware.widget.batchBuildAll'), cls: 'bg-surface' },
  { action: 'flash-all', label: t('firmware.widget.batchFlashAll'), cls: 'bg-brand-yellow' },
  { action: 'flash-ready', label: t('firmware.widget.batchFlashReady'), cls: 'bg-brand-yellow' },
  {
    action: 'build-flash-all',
    label: t('firmware.widget.batchBuildFlash'),
    cls: 'bg-brand-red text-surface',
  },
])
const opLog = ref('')
const opBusy = ref(false)
/** Whose op-log is showing: a device id, or null for the batch log under the batch buttons. */
const activeDeviceId = ref<string | null>(null)
const batchTaskId = ref<string | null>(null)
/** A flash awaiting explicit confirmation (the safety gate) + the action to run on confirm. */
const pendingFlash = ref<FlashIntent | null>(null)
let pendingExec: (() => void) | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null

async function pollTask(): Promise<void> {
  if (!batchTaskId.value) return
  try {
    const task = await fetchTask(batchTaskId.value)
    opLog.value = task.log
    if (task.status === 'running') {
      pollTimer = setTimeout(pollTask, 1200)
    } else {
      opBusy.value = false
      await load(true)
    }
  } catch {
    opBusy.value = false
  }
}

async function runBatch(action: string): Promise<void> {
  if (opBusy.value) return
  error.value = null
  activeDeviceId.value = null
  opLog.value = ''
  opBusy.value = true
  try {
    batchTaskId.value = await startBatch(action)
    await pollTask()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errBatch')
    opBusy.value = false
  }
}

async function cancelBatch(): Promise<void> {
  if (batchTaskId.value) await cancelTask(batchTaskId.value)
}

async function buildDevice(device: Device): Promise<void> {
  if (opBusy.value || !device.profile) return
  error.value = null
  activeDeviceId.value = device.id
  opLog.value = ''
  opBusy.value = true
  try {
    await buildFirmware(device.profile, (chunk) => {
      opLog.value += chunk
    })
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errBuild')
  } finally {
    opBusy.value = false
  }
}

async function rebootDevice(device: Device, rebootMode = 'katapult'): Promise<void> {
  if (opBusy.value) return
  error.value = null
  activeDeviceId.value = device.id
  opLog.value = ''
  opBusy.value = true
  try {
    await rebootBoard(
      { method: device.method, device: device.id, interface: device.interface, mode: rebootMode },
      (chunk) => {
        opLog.value += chunk
      },
    )
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errReboot')
  } finally {
    opBusy.value = false
  }
}

/** True when a profile builds AVR firmware (flashed via `make flash`, not Katapult). */
function isAvr(profile: string | null): boolean {
  return !!profile && (profiles.value.find((p) => p.name === profile)?.is_avr ?? false)
}

function normalizeVer(v: string | null | undefined): string {
  return (v ?? '').replace(/-dirty$/, '')
}

/** The board's actual running firmware, as the live MCU reports it to Moonraker
 *  (NOT the repo build version) — falls back to the recorded flashed version. */
function deviceFirmware(device: Device): string | null {
  return boards.value.find((b) => b.id === device.id)?.version ?? device.flashed_version
}

/** Out of date = the board's running firmware differs from the host's running Klipper. */
function isOutdated(device: Device): boolean {
  const host = normalizeVer(status.value?.host.version)
  const dev = normalizeVer(boards.value.find((b) => b.id === device.id)?.version)
  return host !== '' && dev !== '' && dev !== host
}

/** The flash request for a registered device (profile + connection method + bootloader). */
function flashRequest(device: Device): FlashRequest {
  return {
    profile: device.profile,
    method: isAvr(device.profile) ? 'make' : device.method,
    device: device.id,
    interface: device.interface,
    is_katapult: device.is_katapult,
  }
}

/** Flashes a device's assigned profile directly — uses its already-built artifact.
 *  Not called on click: the flash buttons go through requestFlash() -> the confirm gate. */
async function flashDevice(device: Device): Promise<void> {
  if (opBusy.value || !device.profile) return
  error.value = null
  activeDeviceId.value = device.id
  opLog.value = ''
  opBusy.value = true
  try {
    await flashBoard(flashRequest(device), (chunk) => {
      opLog.value += chunk
    })
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errFlash')
  } finally {
    opBusy.value = false
  }
}

/** Builds a device's profile, then flashes it — but only if the build succeeded. */
async function buildAndFlash(device: Device): Promise<void> {
  if (opBusy.value || !device.profile) return
  error.value = null
  activeDeviceId.value = device.id
  opLog.value = ''
  opBusy.value = true
  try {
    await buildFirmware(device.profile, (chunk) => {
      opLog.value += chunk
    })
    if (!/BUILD OK/i.test(opLog.value)) {
      opLog.value += '\n' + t('firmware.widget.buildFailedSkipFlash') + '\n'
      return
    }
    await flashBoard(flashRequest(device), (chunk) => {
      opLog.value += chunk
    })
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errBuildFlash')
  } finally {
    opBusy.value = false
  }
}

// --- Flash safety gate (#111): every firmware write goes through an explicit plan-preview +
// "I understand" confirm. The buttons set a pending intent; nothing flashes until confirmFlash(). ---
function requestFlash(device: Device): void {
  if (opBusy.value || !device.profile) return
  pendingFlash.value = {
    kind: 'device',
    title: t('firmware.widget.confirmFlashTitle', {
      device: device.name,
      profile: device.profile,
    }),
    warning: t('firmware.widget.confirmFlashWarning'),
    device: device.name,
    request: flashRequest(device),
  }
  pendingExec = () => void flashDevice(device)
}

function requestBuildFlash(device: Device): void {
  if (opBusy.value || !device.profile) return
  pendingFlash.value = {
    kind: 'buildflash',
    title: t('firmware.widget.confirmBuildFlashTitle', {
      profile: device.profile,
      device: device.name,
    }),
    warning: t('firmware.widget.confirmBuildFlashWarning'),
    device: device.name,
  }
  pendingExec = () => void buildAndFlash(device)
}

function requestBatch(action: string): void {
  if (opBusy.value) return
  const label = BATCH_ACTIONS.value.find((b) => b.action === action)?.label ?? action
  const affected = operationalDevices.value
    .filter((d) => action !== 'flash-ready' || liveMode.value[d.id] === 'ready')
    .map((d) => d.name)
  pendingFlash.value = {
    kind: 'batch',
    title: t('firmware.widget.confirmBatchTitle', { label }),
    warning: t('firmware.widget.confirmBatchWarning'),
    devices: affected,
  }
  pendingExec = () => void runBatch(action)
}

function requestBeacon(probe: { id: string; name: string }): void {
  if (beaconFlashing.value) return
  pendingFlash.value = {
    kind: 'beacon',
    title: t('firmware.widget.confirmBeaconTitle', { name: probe.name }),
    warning: t('firmware.widget.confirmBeaconWarning'),
    device: probe.name,
  }
  pendingExec = () => void flashProbe(probe.id)
}

/** Build-all doesn't write firmware, so it bypasses the gate; flashing actions go through it. */
function runBatchGated(action: string): void {
  if (action === 'build-all') void runBatch(action)
  else requestBatch(action)
}

function confirmFlash(): void {
  const exec = pendingExec
  pendingFlash.value = null
  pendingExec = null
  exec?.()
}

function cancelFlash(): void {
  pendingFlash.value = null
  pendingExec = null
}

async function flashProbe(device: string): Promise<void> {
  if (beaconFlashing.value) return
  beaconFlashing.value = true
  beaconLog.value = ''
  error.value = null
  try {
    await flashBeacon(device, (chunk) => {
      beaconLog.value += chunk
    })
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errBeaconFlash')
  } finally {
    beaconFlashing.value = false
  }
}

async function doService(action: string): Promise<void> {
  servicesBusy.value = true
  error.value = null
  try {
    await manageServices(action)
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.widget.errService')
  } finally {
    servicesBusy.value = false
  }
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  // First-run: if no board is set up yet, land on the Guided walkthrough (#118).
  void load().then(() => {
    if (operationalDevices.value.length === 0) mode.value = 'guided'
  })
  // Keep live status fresh while the widget is open (silent refreshes).
  timer = setInterval(() => void load(true), 6000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- One "guide" button (the organised home for all help), reachable from every tab. -->
    <div class="flex justify-end">
      <HelpDrawer
        namespace="firmware"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        steps-key="firmware.widget.steps"
        :button-label="t('firmware.help.guide')"
        :title="t('firmware.help.guideTitle')"
        :close-label="t('firmware.help.close')"
        :steps-title="t('firmware.help.howToRead')"
      />
    </div>

    <!-- House navigation: one persistent tab strip (#117) — replaces the footer-button nav. -->
    <WidgetTabs v-model="mode" :tabs="FW_TABS" />

    <div v-if="mode === 'guided'" class="space-y-2">
      <HelpNote topic="guided" />
      <FirmwareGuided
        :boards-scanned="boards.length"
        :built-profiles="builtProfileCount"
        :operational="operationalDevices.length"
        :outdated="outdatedCount"
        @go="mode = $event"
      />
    </div>
    <div v-else-if="mode === 'configure'" class="space-y-2">
      <HelpNote topic="configure" />
      <FirmwareConfigEditor @close="mode = 'status'" />
    </div>
    <FirmwareDevicesPanel v-else-if="mode === 'devices'" @close="mode = 'status'" />
    <div v-else-if="mode === 'external'" class="space-y-2">
      <HelpNote topic="external" />
      <ExternalFirmwarePanel />
    </div>
    <template v-else>
      <div v-if="loading && !status" class="font-mono text-xs">
        {{ t('firmware.widget.loading') }}
      </div>
      <div
        v-else-if="error"
        class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red px-2 py-1 text-surface"
      >
        <span class="min-w-0 flex-1 text-[11px]">{{ error }}</span>
        <button
          class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[11px] text-ink"
          :disabled="loading"
          @click="load()"
        >
          {{ loading ? t('firmware.widget.retrying') : t('firmware.widget.retry') }}
        </button>
      </div>

      <template v-else-if="status">
        <div class="space-y-1.5">
          <!-- Host runs the Klipper host software — the reference every MCU syncs to. -->
          <div
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-cyan px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate font-bold">{{
              t('firmware.widget.hostKlipper')
            }}</span>
            <span class="font-mono text-[11px] opacity-80">{{ status.host.version ?? '—' }}</span>
            <span class="nb-badge shrink-0 bg-surface">{{
              status.host.state ?? t('firmware.widget.hostFallback')
            }}</span>
          </div>
        </div>

        <div class="flex flex-wrap gap-1.5 border-t-2 border-ink pt-2">
          <span
            v-for="tool in TOOLS"
            :key="tool.key"
            class="nb-badge"
            :class="status.tools[tool.key] ? 'bg-brand-lime' : 'bg-surface opacity-60'"
          >
            {{ status.tools[tool.key] ? '✓' : '✗' }} {{ tool.label }}
          </span>
          <span
            v-if="health"
            class="nb-badge text-[11px]"
            :class="health.healthy ? 'bg-brand-lime' : 'bg-brand-yellow'"
            :title="healthTitle || t('firmware.widget.healthOkTitle')"
          >
            {{
              health.healthy
                ? t('firmware.widget.healthOk')
                : t('firmware.widget.healthIssues', { n: healthIssues.length }, healthIssues.length)
            }}
          </span>
        </div>

        <div class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">{{
              t('firmware.widget.servicesHeading')
            }}</span>
            <div class="flex gap-1">
              <button
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="servicesBusy"
                @click="doService('start')"
              >
                {{ t('firmware.widget.svcStart') }}
              </button>
              <button
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="servicesBusy"
                @click="doService('stop')"
              >
                {{ t('firmware.widget.svcStop') }}
              </button>
              <button
                class="nb-btn bg-brand-cyan px-2 py-0.5 text-[11px]"
                :disabled="servicesBusy"
                @click="doService('restart')"
              >
                {{ t('firmware.widget.svcRestart') }}
              </button>
            </div>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="s in services"
              :key="s.name"
              class="nb-badge text-[11px]"
              :class="s.active ? 'bg-brand-lime' : 'bg-surface opacity-60'"
            >
              {{ s.active ? '●' : '○' }} {{ s.name }}
            </span>
            <span v-if="!services.length" class="font-mono text-[11px] opacity-60">
              {{ t('firmware.widget.noServices') }}
            </span>
          </div>
        </div>

        <div v-if="beacon?.probes.length" class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">{{
              t('firmware.widget.beaconHeading')
            }}</span>
            <span v-if="beacon.available_version" class="font-mono text-[11px] opacity-60">
              {{ t('firmware.widget.beaconAvailable', { version: beacon.available_version }) }}
            </span>
          </div>
          <div
            v-for="p in beacon.probes"
            :key="p.serial"
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate font-bold">{{ p.name }}</span>
            <span class="shrink-0 font-mono text-[10px] uppercase opacity-50">beacon</span>
            <button
              class="nb-btn shrink-0 bg-brand-yellow px-2 py-0.5 text-[11px]"
              :disabled="beaconFlashing"
              @click="requestBeacon(p)"
            >
              {{ beaconFlashing ? t('firmware.widget.flashing') : t('firmware.widget.flash') }}
            </button>
          </div>
          <LogPane v-if="beaconLog" :log="beaconLog" max-class="max-h-40" />
        </div>

        <!-- Your registered devices: the operational view (configure them in the manager). -->
        <div class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">{{
              t('firmware.widget.devicesHeading')
            }}</span>
            <button
              v-if="opBusy"
              class="nb-btn bg-brand-red px-2 py-0.5 text-[11px] text-surface"
              @click="cancelBatch"
            >
              {{ t('firmware.widget.cancel') }}
            </button>
          </div>

          <div v-if="operationalDevices.length" class="flex flex-wrap gap-1.5">
            <button
              v-for="b in BATCH_ACTIONS"
              :key="b.action"
              class="nb-btn px-2 py-0.5 text-[11px]"
              :class="b.cls"
              :disabled="opBusy"
              @click="runBatchGated(b.action)"
            >
              {{ b.label }}
            </button>
          </div>

          <LogPane v-if="opLog && activeDeviceId === null" :log="opLog" />

          <div
            v-for="device in operationalDevices"
            :key="device.id"
            class="space-y-1 rounded-brutal border-2 border-ink px-2 py-1.5"
          >
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 truncate font-bold">{{ device.name }}</span>
              <span
                class="nb-badge shrink-0 text-[10px]"
                :class="boardModeClass(liveMode[device.id] ?? 'offline')"
                >{{ liveMode[device.id] ?? 'offline' }}</span
              >
              <span class="shrink-0 font-mono text-[10px] uppercase opacity-50">{{
                device.method
              }}</span>
            </div>
            <div class="flex items-center justify-between gap-2 font-mono text-[10px] opacity-60">
              <span class="truncate">{{
                device.profile
                  ? t('firmware.widget.profileLabel', { profile: device.profile })
                  : t('firmware.widget.noProfileAssigned')
              }}</span>
              <span class="flex shrink-0 items-center gap-1">
                <span
                  v-if="isOutdated(device)"
                  class="nb-badge bg-brand-red text-surface opacity-100"
                  :title="t('firmware.widget.outdatedTitle')"
                >
                  {{ t('firmware.widget.updateBadge') }}
                </span>
                <span v-if="deviceFirmware(device)">{{ deviceFirmware(device) }}</span>
              </span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <button
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="opBusy || !device.profile"
                @click="buildDevice(device)"
              >
                {{ t('firmware.widget.build') }}
              </button>
              <button
                class="nb-btn bg-brand-yellow px-2 py-0.5 text-[11px]"
                :disabled="opBusy || !device.profile"
                @click="requestFlash(device)"
              >
                {{ t('firmware.widget.flash') }}
              </button>
              <button
                class="nb-btn bg-brand-red px-2 py-0.5 text-[11px] text-surface"
                :disabled="opBusy || !device.profile"
                @click="requestBuildFlash(device)"
              >
                {{ t('firmware.widget.buildFlash') }}
              </button>
              <button
                v-if="device.method === 'serial' || device.method === 'can'"
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="opBusy"
                @click="rebootDevice(device, 'katapult')"
              >
                {{ t('firmware.widget.boot') }}
              </button>
            </div>

            <LogPane v-if="opLog && activeDeviceId === device.id" :log="opLog" />
          </div>
          <div v-if="!operationalDevices.length" class="space-y-1.5">
            <p class="font-mono text-xs opacity-70">
              {{ t('firmware.widget.noDevices') }}
            </p>
            <button class="nb-btn bg-brand-lime px-2 py-0.5 text-[11px]" @click="mode = 'devices'">
              {{ t('firmware.widget.addFirstBoard') }}
            </button>
          </div>
        </div>
      </template>

      <p v-else class="font-mono text-xs opacity-70">
        {{ t('firmware.widget.noStatus') }}
      </p>
    </template>

    <!-- Flash safety gate: nothing writes firmware until the user confirms here (#111). -->
    <FirmwareFlashConfirm
      v-if="pendingFlash"
      :intent="pendingFlash"
      @confirm="confirmFlash"
      @cancel="cancelFlash"
    />
  </div>
</template>
