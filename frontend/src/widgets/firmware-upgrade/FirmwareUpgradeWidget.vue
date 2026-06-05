<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import WidgetTabs from '@/components/ui/WidgetTabs.vue'

import ExternalFirmwarePanel from './ExternalFirmwarePanel.vue'
import FirmwareConfigEditor from './FirmwareConfigEditor.vue'
import FirmwareGuided from './FirmwareGuided.vue'
import FirmwareDevicesPanel from './FirmwareDevicesPanel.vue'
import FirmwareFlashConfirm from './FirmwareFlashConfirm.vue'
import HelpNote from './HelpNote.vue'
import { STEPS } from './help'
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

type FwMode = 'guided' | 'status' | 'configure' | 'devices' | 'external'
const mode = ref<FwMode>('status')
const FW_TABS: { id: FwMode; label: string }[] = [
  { id: 'guided', label: '🧭 Guided' },
  { id: 'status', label: '🩺 Status' },
  { id: 'configure', label: '🔧 Configure' },
  { id: 'devices', label: '🖥 Devices' },
  { id: 'external', label: '📦 External' },
]
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
const showSteps = ref(false)

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

/** Maps a raw fetch failure to a clear, actionable message. */
function describeError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|fetch/i.test(m)) {
    return 'Cannot reach the FilaMind backend — check that the filamind-flow service is running and reachable.'
  }
  return m
}

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
const BATCH_ACTIONS = [
  { action: 'build-all', label: 'Build all', cls: 'bg-surface' },
  { action: 'flash-all', label: 'Flash all', cls: 'bg-brand-yellow' },
  { action: 'flash-ready', label: 'Flash ready', cls: 'bg-brand-yellow' },
  { action: 'build-flash-all', label: 'Build & flash', cls: 'bg-brand-red text-surface' },
]
const opLog = ref('')
const opBusy = ref(false)
/** Whose op-log is showing: a device id, or null for the batch log under the batch buttons. */
const activeDeviceId = ref<string | null>(null)
const batchTaskId = ref<string | null>(null)
/** A flash awaiting explicit confirmation (the safety gate) + the action to run on confirm. */
const pendingFlash = ref<FlashIntent | null>(null)
let pendingExec: (() => void) | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null

const opLines = computed(() => opLog.value.split('\n'))

function opLineClass(line: string): string {
  if (line.startsWith('!!') || /fail/i.test(line)) return 'text-brand-red'
  if (line.includes('=====') || /\bOK\b|complete|successful/i.test(line)) return 'text-brand-lime'
  if (line.startsWith('>>>')) return 'text-brand-cyan'
  return 'text-surface opacity-80'
}

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
    error.value = e instanceof Error ? e.message : 'Batch failed'
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
    error.value = e instanceof Error ? e.message : 'Build failed'
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
    error.value = e instanceof Error ? e.message : 'Reboot failed'
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
    error.value = e instanceof Error ? e.message : 'Flash failed'
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
      opLog.value += '\n!! Build did not succeed — skipping flash.\n'
      return
    }
    await flashBoard(flashRequest(device), (chunk) => {
      opLog.value += chunk
    })
    await load(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Build & flash failed'
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
    title: `Flash ${device.name} with “${device.profile}”.`,
    warning: 'Keep power stable and don’t unplug — interrupting a flash can brick the board.',
    device: device.name,
    request: flashRequest(device),
  }
  pendingExec = () => void flashDevice(device)
}

function requestBuildFlash(device: Device): void {
  if (opBusy.value || !device.profile) return
  pendingFlash.value = {
    kind: 'buildflash',
    title: `Build “${device.profile}”, then flash ${device.name}.`,
    warning:
      'This rebuilds the firmware and writes it to the board — keep power stable until done.',
    device: device.name,
  }
  pendingExec = () => void buildAndFlash(device)
}

function requestBatch(action: string): void {
  if (opBusy.value) return
  const label = BATCH_ACTIONS.find((b) => b.action === action)?.label ?? action
  const affected = operationalDevices.value
    .filter((d) => action !== 'flash-ready' || liveMode.value[d.id] === 'ready')
    .map((d) => d.name)
  pendingFlash.value = {
    kind: 'batch',
    title: `${label} — this flashes multiple devices in turn.`,
    warning: 'Keep power stable until every device finishes — interrupting any flash can brick it.',
    devices: affected,
  }
  pendingExec = () => void runBatch(action)
}

function requestBeacon(probe: { id: string; name: string }): void {
  if (beaconFlashing.value) return
  pendingFlash.value = {
    kind: 'beacon',
    title: `Flash the Beacon probe ${probe.name}.`,
    warning: 'Keep the probe connected and powered — interrupting the flash can brick it.',
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
    error.value = e instanceof Error ? e.message : 'Beacon flash failed'
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
    error.value = e instanceof Error ? e.message : 'Service action failed'
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
      <div v-if="loading && !status" class="font-mono text-xs">Loading firmware status…</div>
      <div
        v-else-if="error"
        class="flex flex-wrap items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-red px-2 py-1 text-surface"
      >
        <span class="min-w-0 flex-1 text-[11px]">{{ error }}</span>
        <button
          class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[10px] text-ink"
          :disabled="loading"
          @click="load()"
        >
          {{ loading ? 'retrying…' : '↻ retry' }}
        </button>
      </div>

      <template v-else-if="status">
        <!-- Help layer (collapsed by default — the project widget-UX rule) -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <HelpNote topic="overview" />
          <HelpNote topic="glossary" />
          <HelpNote topic="status" />
          <HelpNote topic="toolchain" />
          <HelpNote topic="services" />
          <HelpNote topic="devices" />
          <HelpNote topic="flash" />
          <button
            class="font-mono text-[10px] opacity-60 transition-opacity hover:opacity-100"
            :aria-expanded="showSteps"
            @click="showSteps = !showSteps"
          >
            {{ showSteps ? '▾ build → flash guide' : '▸ build → flash guide' }}
          </button>
        </div>
        <ol
          v-if="showSteps"
          class="list-decimal space-y-1 rounded-brutal border-2 border-dashed border-ink bg-paper py-2 pl-6 pr-2 text-[11px] leading-snug opacity-80"
        >
          <li v-for="(s, i) in STEPS" :key="i">{{ s }}</li>
        </ol>

        <div class="space-y-1.5">
          <!-- Host runs the Klipper host software — the reference every MCU syncs to. -->
          <div
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink bg-brand-cyan px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate font-bold">Host · Klipper</span>
            <span class="font-mono text-[11px] opacity-80">{{ status.host.version ?? '—' }}</span>
            <span class="nb-badge shrink-0 bg-surface">{{ status.host.state ?? 'host' }}</span>
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
            class="nb-badge text-[10px]"
            :class="health.healthy ? 'bg-brand-lime' : 'bg-brand-yellow'"
            :title="healthTitle || 'host is set up for flashing'"
          >
            {{
              health.healthy
                ? '✓ setup'
                : `${healthIssues.length} setup issue${healthIssues.length === 1 ? '' : 's'}`
            }}
          </span>
        </div>

        <div class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">Services</span>
            <div class="flex gap-1">
              <button
                class="nb-btn px-2 py-0.5 text-[10px]"
                :disabled="servicesBusy"
                @click="doService('start')"
              >
                start
              </button>
              <button
                class="nb-btn px-2 py-0.5 text-[10px]"
                :disabled="servicesBusy"
                @click="doService('stop')"
              >
                stop
              </button>
              <button
                class="nb-btn bg-brand-cyan px-2 py-0.5 text-[10px]"
                :disabled="servicesBusy"
                @click="doService('restart')"
              >
                restart
              </button>
            </div>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="s in services"
              :key="s.name"
              class="nb-badge text-[10px]"
              :class="s.active ? 'bg-brand-lime' : 'bg-surface opacity-60'"
            >
              {{ s.active ? '●' : '○' }} {{ s.name }}
            </span>
            <span v-if="!services.length" class="font-mono text-[10px] opacity-60">
              no services detected
            </span>
          </div>
        </div>

        <div v-if="beacon?.probes.length" class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">Beacon</span>
            <span v-if="beacon.available_version" class="font-mono text-[10px] opacity-60">
              available {{ beacon.available_version }}
            </span>
          </div>
          <div
            v-for="p in beacon.probes"
            :key="p.serial"
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate font-bold">{{ p.name }}</span>
            <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">beacon</span>
            <button
              class="nb-btn shrink-0 bg-brand-yellow px-2 py-0.5 text-[10px]"
              :disabled="beaconFlashing"
              @click="requestBeacon(p)"
            >
              {{ beaconFlashing ? 'flashing…' : 'flash' }}
            </button>
          </div>
          <pre
            v-if="beaconLog"
            class="max-h-40 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight text-surface"
            >{{ beaconLog }}</pre
          >
        </div>

        <!-- Your registered devices: the operational view (configure them in the manager). -->
        <div class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">Devices</span>
            <button
              v-if="opBusy"
              class="nb-btn bg-brand-red px-2 py-0.5 text-[10px] text-surface"
              @click="cancelBatch"
            >
              cancel
            </button>
          </div>

          <div v-if="operationalDevices.length" class="flex flex-wrap gap-1.5">
            <button
              v-for="b in BATCH_ACTIONS"
              :key="b.action"
              class="nb-btn px-2 py-0.5 text-[10px]"
              :class="b.cls"
              :disabled="opBusy"
              @click="runBatchGated(b.action)"
            >
              {{ b.label }}
            </button>
          </div>

          <div
            v-if="opLog && activeDeviceId === null"
            class="max-h-48 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight"
          >
            <div
              v-for="(line, i) in opLines"
              :key="i"
              :class="['whitespace-pre-wrap break-all', opLineClass(line)]"
            >
              {{ line }}
            </div>
          </div>

          <div
            v-for="device in operationalDevices"
            :key="device.id"
            class="space-y-1 rounded-brutal border-2 border-ink px-2 py-1.5"
          >
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 truncate font-bold">{{ device.name }}</span>
              <span
                class="nb-badge shrink-0 text-[9px]"
                :class="boardModeClass(liveMode[device.id] ?? 'offline')"
                >{{ liveMode[device.id] ?? 'offline' }}</span
              >
              <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">{{
                device.method
              }}</span>
            </div>
            <div class="flex items-center justify-between gap-2 font-mono text-[9px] opacity-60">
              <span class="truncate">{{
                device.profile ? 'profile: ' + device.profile : 'no profile assigned'
              }}</span>
              <span class="flex shrink-0 items-center gap-1">
                <span
                  v-if="isOutdated(device)"
                  class="nb-badge bg-brand-red text-surface opacity-100"
                  title="Running firmware differs from the host's Klipper — build &amp; flash to update"
                >
                  ⚠ update
                </span>
                <span v-if="deviceFirmware(device)">{{ deviceFirmware(device) }}</span>
              </span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <button
                class="nb-btn px-2 py-0.5 text-[10px]"
                :disabled="opBusy || !device.profile"
                @click="buildDevice(device)"
              >
                build
              </button>
              <button
                class="nb-btn bg-brand-yellow px-2 py-0.5 text-[10px]"
                :disabled="opBusy || !device.profile"
                @click="requestFlash(device)"
              >
                flash
              </button>
              <button
                class="nb-btn bg-brand-red px-2 py-0.5 text-[10px] text-surface"
                :disabled="opBusy || !device.profile"
                @click="requestBuildFlash(device)"
              >
                build &amp; flash
              </button>
              <button
                v-if="device.method === 'serial' || device.method === 'can'"
                class="nb-btn px-2 py-0.5 text-[10px]"
                :disabled="opBusy"
                @click="rebootDevice(device, 'katapult')"
              >
                boot
              </button>
            </div>

            <div
              v-if="opLog && activeDeviceId === device.id"
              class="max-h-48 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight"
            >
              <div
                v-for="(line, i) in opLines"
                :key="i"
                :class="['whitespace-pre-wrap break-all', opLineClass(line)]"
              >
                {{ line }}
              </div>
            </div>
          </div>
          <div v-if="!operationalDevices.length" class="space-y-1.5">
            <p class="font-mono text-xs opacity-70">
              No devices yet — add a board and assign it a profile to build &amp; flash it here.
            </p>
            <button class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]" @click="mode = 'devices'">
              + Add your first board →
            </button>
          </div>
        </div>
      </template>

      <p v-else class="font-mono text-xs opacity-70">
        No firmware status yet — couldn't reach the backend.
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
