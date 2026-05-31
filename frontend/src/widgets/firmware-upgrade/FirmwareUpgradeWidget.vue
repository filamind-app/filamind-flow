<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import FirmwareConfigEditor from './FirmwareConfigEditor.vue'
import FirmwareDevicesPanel from './FirmwareDevicesPanel.vue'
import FirmwareFlashPanel from './FirmwareFlashPanel.vue'
import {
  fetchBeacon,
  fetchBoards,
  fetchFirmwareStatus,
  fetchServices,
  flashBeacon,
  manageServices,
} from './api'
import type {
  BeaconResponse,
  Board,
  BoardDiscovery,
  FirmwareStatus,
  FirmwareTools,
  ServiceInfo,
} from './types'

const mode = ref<'status' | 'configure' | 'devices'>('status')
const flashTarget = ref<Board | null>(null)
const status = ref<FirmwareStatus | null>(null)
const boards = ref<BoardDiscovery | null>(null)
const services = ref<ServiceInfo[]>([])
const servicesBusy = ref(false)
const beacon = ref<BeaconResponse | null>(null)
const beaconLog = ref('')
const beaconFlashing = ref(false)
const error = ref<string | null>(null)
const loading = ref(true)

function boardModeClass(mode: string): string {
  if (mode === 'service') return 'bg-brand-lime'
  if (mode === 'ready' || mode === 'dfu') return 'bg-brand-yellow'
  return 'bg-surface opacity-70'
}

/** Explicit status for the optional Klipper 'Linux process' host MCU. */
const hostMcu = computed(() => {
  const h = status.value?.host_mcu
  if (h?.configured) return { label: 'active', cls: 'bg-brand-lime' }
  if (h?.service_active) return { label: 'available · not configured', cls: 'bg-brand-yellow' }
  return { label: 'not installed', cls: 'bg-surface opacity-60' }
})

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
    const [statusData, boardsData] = await Promise.all([fetchFirmwareStatus(), fetchBoards()])
    status.value = statusData
    boards.value = boardsData
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

          <div
            v-for="mcu in status.mcus"
            :key="mcu.name"
            class="rounded-brutal border-2 border-ink px-2 py-1"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="min-w-0 flex-1 truncate font-bold">{{ mcu.name }}</span>
              <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">{{ mcu.kind }}</span>
              <span class="font-mono text-[11px] opacity-80">{{ mcu.version ?? '—' }}</span>
              <span
                class="nb-badge shrink-0"
                :class="
                  mcu.in_sync === false
                    ? 'bg-brand-red text-surface'
                    : mcu.in_sync
                      ? 'bg-brand-lime'
                      : 'bg-surface'
                "
              >
                {{ mcu.in_sync === false ? 'mismatch' : mcu.in_sync ? 'in sync' : '—' }}
              </span>
            </div>
            <div
              v-if="mcu.freq"
              class="mt-0.5 flex flex-wrap gap-x-2 font-mono text-[9px] opacity-60"
            >
              <span>{{ Math.round(mcu.freq / 1e6) }} MHz</span>
              <span v-if="mcu.awake != null">· {{ (mcu.awake * 100).toFixed(1) }}% load</span>
              <span
                v-if="mcu.retransmits != null"
                :class="mcu.retransmits > 0 ? 'text-brand-red opacity-100' : ''"
              >
                · {{ mcu.retransmits }} retransmit{{ mcu.retransmits === 1 ? '' : 's' }}
              </span>
            </div>
          </div>

          <p v-if="!status.mcus.length" class="font-mono text-xs opacity-70">
            {{ status.reachable ? 'No MCUs reported.' : 'Printer not reachable.' }}
          </p>
        </div>

        <div class="flex items-center justify-between gap-2 border-t-2 border-ink pt-2 text-xs">
          <span class="font-bold">Linux host MCU</span>
          <span v-if="status.host_mcu.version" class="font-mono text-[11px] opacity-80">{{
            status.host_mcu.version
          }}</span>
          <span class="nb-badge shrink-0" :class="hostMcu.cls">{{ hostMcu.label }}</span>
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

        <div v-if="boards" class="space-y-1.5 border-t-2 border-ink pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wide">Detected boards</span>
            <span class="font-mono text-[10px] opacity-60">{{ boards.boards.length }} found</span>
          </div>
          <div
            v-for="board in boards.boards"
            :key="board.id"
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate font-bold">{{ board.name }}</span>
            <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">{{
              board.connection
            }}</span>
            <span
              v-if="board.version || board.flashed_version"
              class="shrink-0 truncate font-mono text-[9px] opacity-60"
            >
              {{ board.version ?? board.flashed_version }}
            </span>
            <span v-if="board.configured" class="nb-badge shrink-0 bg-surface text-[9px]">cfg</span>
            <span class="nb-badge shrink-0" :class="boardModeClass(board.mode)">{{
              board.mode
            }}</span>
            <button class="nb-btn shrink-0 px-2 py-0.5 text-[10px]" @click="flashTarget = board">
              flash
            </button>
          </div>
          <p v-if="!boards.boards.length" class="font-mono text-xs opacity-70">
            No flashable boards detected.
          </p>
        </div>

        <div class="flex gap-2">
          <button class="nb-btn flex-1 bg-brand-yellow py-1 text-xs" @click="mode = 'devices'">
            Devices →
          </button>
          <button class="nb-btn flex-1 bg-brand-cyan py-1 text-xs" @click="mode = 'configure'">
            Configure →
          </button>
        </div>
      </template>
    </template>
  </div>
</template>
