<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import FirmwareConfigEditor from './FirmwareConfigEditor.vue'
import FirmwareDevicesPanel from './FirmwareDevicesPanel.vue'
import FirmwareFlashPanel from './FirmwareFlashPanel.vue'
import {
  buildFirmware,
  cancelTask,
  fetchBeacon,
  fetchBoards,
  fetchDevices,
  fetchFirmwareStatus,
  fetchHealth,
  fetchServices,
  fetchTask,
  flashBeacon,
  manageServices,
  rebootBoard,
  startBatch,
} from './api'
import type {
  BeaconResponse,
  Board,
  Device,
  FirmwareStatus,
  FirmwareTools,
  HealthReport,
  ServiceInfo,
} from './types'

const mode = ref<'status' | 'configure' | 'devices'>('status')
const flashTarget = ref<Board | null>(null)
const status = ref<FirmwareStatus | null>(null)
const boards = ref<Board[]>([])
const devices = ref<Device[]>([])
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
  error.value = null
  try {
    const [statusData, boardsData, devicesData] = await Promise.all([
      fetchFirmwareStatus(),
      fetchBoards(),
      fetchDevices(),
    ])
    status.value = statusData
    boards.value = boardsData.boards
    devices.value = devicesData.devices
  } catch (e) {
    if (!silent) error.value = e instanceof Error ? e.message : 'Failed to load firmware status'
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
const batchTaskId = ref<string | null>(null)
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

/** Opens the flash panel for a registered device (reuses the board-based panel). */
function openFlash(device: Device): void {
  flashTarget.value = {
    id: device.id,
    name: device.name,
    mcu_name: null,
    connection: device.method,
    mode: liveMode.value[device.id] ?? 'unknown',
    configured: false,
    version: device.flashed_version,
    application: null,
    interface: device.interface,
    flashed_version: device.flashed_version,
    managed: true,
  }
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
  void load()
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
    <FirmwareFlashPanel v-if="flashTarget" :board="flashTarget" @close="flashTarget = null" />
    <FirmwareConfigEditor v-else-if="mode === 'configure'" @close="mode = 'status'" />
    <FirmwareDevicesPanel v-else-if="mode === 'devices'" @close="mode = 'status'" />
    <template v-else>
      <div v-if="loading" class="font-mono text-xs">Loading firmware status…</div>
      <div v-else-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

      <template v-else-if="status">
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
              @click="flashProbe(p.id)"
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
              @click="runBatch(b.action)"
            >
              {{ b.label }}
            </button>
          </div>

          <div
            v-if="opLog"
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
              <span v-if="device.flashed_version" class="shrink-0">{{
                device.flashed_version
              }}</span>
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
                :disabled="!device.profile"
                @click="openFlash(device)"
              >
                flash →
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
          </div>
          <p v-if="!operationalDevices.length" class="font-mono text-xs opacity-70">
            No devices yet — add a board and assign it a profile in the Devices manager.
          </p>
        </div>

        <div class="flex gap-2">
          <button class="nb-btn flex-1 bg-brand-yellow py-1 text-xs" @click="mode = 'devices'">
            Devices manager →
          </button>
          <button class="nb-btn flex-1 bg-brand-cyan py-1 text-xs" @click="mode = 'configure'">
            Configure →
          </button>
        </div>
      </template>
    </template>
  </div>
</template>
