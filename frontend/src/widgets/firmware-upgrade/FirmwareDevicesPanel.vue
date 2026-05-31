<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import {
  attachIdentity,
  cancelTask,
  fetchBoards,
  fetchDevices,
  fetchProfiles,
  fetchTask,
  rebootBoard,
  removeDevice,
  saveDevice,
  startBatch,
} from './api'
import type { Board, FirmwareProfile, Device } from './types'

defineEmits<{ close: [] }>()

const devices = ref<Device[]>([])
const boards = ref<Board[]>([])
const profiles = ref<FirmwareProfile[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
/** Id of the discovered board currently choosing a device to attach to. */
const attachFor = ref<string | null>(null)

const METHODS = ['serial', 'can', 'dfu', 'linux']
const BAUDRATES = [115200, 230400, 250000, 500000, 1000000]
const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

/** Boards on the bus that are not yet saved in the registry. */
const unmanaged = computed(() => boards.value.filter((b) => !b.managed))

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [devicesData, boardData, profileData] = await Promise.all([
      fetchDevices(),
      fetchBoards(),
      fetchProfiles(),
    ])
    devices.value = devicesData.devices
    boards.value = boardData.boards
    profiles.value = profileData.profiles
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load devices'
  } finally {
    loading.value = false
  }
}

async function persist(device: Device): Promise<void> {
  error.value = null
  try {
    await saveDevice({ ...device })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Save failed'
  }
}

function methodForBoard(board: Board): string {
  return board.connection === 'usb' || board.connection === 'serial' ? 'serial' : board.connection
}

async function addBoard(board: Board): Promise<void> {
  error.value = null
  try {
    await saveDevice({
      id: board.id,
      name: board.name,
      method: methodForBoard(board),
      interface: board.interface ?? 'can0',
      profile: null,
    })
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Add failed'
  }
}

async function attachToDevice(board: Board, deviceId: string): Promise<void> {
  error.value = null
  try {
    await attachIdentity(deviceId, board.id, board.connection === 'dfu' ? 'dfu' : 'serial')
    attachFor.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Attach failed'
  }
}

async function detach(device: Device, field: 'serial_id' | 'dfu_id'): Promise<void> {
  device[field] = null
  await persist(device)
}

async function remove(device: Device): Promise<void> {
  error.value = null
  try {
    await removeDevice(device.id)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Remove failed'
  }
}

// --- Batch operations (build / flash every device, with a cancellable log) ---
const BATCH_ACTIONS = [
  { action: 'build-all', label: 'Build all', cls: 'bg-surface' },
  { action: 'flash-all', label: 'Flash all', cls: 'bg-brand-yellow' },
  { action: 'flash-ready', label: 'Flash ready', cls: 'bg-brand-yellow' },
  { action: 'build-flash-all', label: 'Build & flash', cls: 'bg-brand-red text-surface' },
]
const batchLog = ref('')
const batchRunning = ref(false)
const batchTaskId = ref<string | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const batchLines = computed(() => batchLog.value.split('\n'))

function batchLineClass(line: string): string {
  if (line.startsWith('!!') || /fail/i.test(line)) return 'text-brand-red'
  if (line.includes('=====') || /\bOK\b|complete|successful/i.test(line)) return 'text-brand-lime'
  if (line.startsWith('>>>')) return 'text-brand-cyan'
  return 'text-surface opacity-80'
}

async function poll(): Promise<void> {
  if (!batchTaskId.value) return
  try {
    const task = await fetchTask(batchTaskId.value)
    batchLog.value = task.log
    if (task.status === 'running') {
      pollTimer = setTimeout(poll, 1200)
    } else {
      batchRunning.value = false
      await load()
    }
  } catch {
    batchRunning.value = false
  }
}

async function runBatch(action: string): Promise<void> {
  if (batchRunning.value) return
  error.value = null
  batchLog.value = ''
  batchRunning.value = true
  try {
    batchTaskId.value = await startBatch(action)
    await poll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Batch failed'
    batchRunning.value = false
  }
}

async function cancelBatch(): Promise<void> {
  if (batchTaskId.value) await cancelTask(batchTaskId.value)
}

// --- Live status + per-device reboot-to-bootloader ---
const liveMode = computed(() => {
  const map: Record<string, string> = {}
  for (const b of boards.value) map[b.id] = b.mode
  return map
})

function modeClass(mode: string): string {
  if (mode === 'service') return 'bg-brand-lime'
  if (mode === 'ready' || mode === 'dfu') return 'bg-brand-yellow'
  return 'bg-surface opacity-60'
}

async function rebootDevice(device: Device): Promise<void> {
  if (batchRunning.value) return
  error.value = null
  batchLog.value = ''
  batchRunning.value = true
  try {
    await rebootBoard(
      { method: device.method, device: device.id, interface: device.interface },
      (chunk) => {
        batchLog.value += chunk
      },
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Reboot failed'
  } finally {
    batchRunning.value = false
    await load()
  }
}

// Refresh only the live board modes on a timer — never the editable device rows.
let boardsTimer: ReturnType<typeof setInterval> | null = null
async function refreshBoards(): Promise<void> {
  try {
    boards.value = (await fetchBoards()).boards
  } catch {
    /* transient — keep the last good modes */
  }
}

onMounted(() => {
  void load()
  boardsTimer = setInterval(refreshBoards, 6000)
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
  if (boardsTimer) clearInterval(boardsTimer)
})
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">Devices</span>
      <button class="nb-btn px-2 py-0.5 text-xs" @click="$emit('close')">← back</button>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
    <div v-if="loading" class="font-mono text-xs">Loading devices…</div>

    <template v-else>
      <!-- Batch operations across every registered device -->
      <div class="space-y-1.5 rounded-brutal border-2 border-ink p-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold uppercase tracking-wide">Batch</span>
          <button
            v-if="batchRunning"
            class="nb-btn bg-brand-red px-2 py-0.5 text-[10px] text-surface"
            @click="cancelBatch"
          >
            cancel
          </button>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="b in BATCH_ACTIONS"
            :key="b.action"
            class="nb-btn px-2 py-0.5 text-[10px]"
            :class="b.cls"
            :disabled="batchRunning"
            @click="runBatch(b.action)"
          >
            {{ b.label }}
          </button>
        </div>
        <div
          v-if="batchLog"
          class="max-h-56 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight"
        >
          <div
            v-for="(line, i) in batchLines"
            :key="i"
            :class="['whitespace-pre-wrap break-all', batchLineClass(line)]"
          >
            {{ line }}
          </div>
        </div>
      </div>

      <!-- Registered devices -->
      <div
        v-for="device in devices"
        :key="device.id"
        class="space-y-1.5 rounded-brutal border-2 border-ink p-2"
      >
        <div class="flex items-center gap-2">
          <input
            v-model="device.name"
            :class="['min-w-0 flex-1 font-bold', inputClass]"
            @change="persist(device)"
          />
          <span
            class="nb-badge shrink-0 text-[9px]"
            :class="modeClass(liveMode[device.id] ?? 'offline')"
          >
            {{ liveMode[device.id] ?? 'offline' }}
          </span>
          <span v-if="device.flashed_version" class="shrink-0 font-mono text-[9px] opacity-60">{{
            device.flashed_version
          }}</span>
          <button
            v-if="device.method === 'serial' || device.method === 'can'"
            class="nb-btn shrink-0 px-2 py-0.5 text-[10px]"
            :disabled="batchRunning"
            @click="rebootDevice(device)"
          >
            boot
          </button>
          <button
            class="nb-btn shrink-0 bg-brand-red px-2 py-0.5 text-[10px] text-surface"
            @click="remove(device)"
          >
            remove
          </button>
        </div>
        <div class="font-mono text-[9px] opacity-50">{{ device.id }}</div>

        <div class="flex flex-wrap items-center gap-1.5">
          <select v-model="device.profile" :class="inputClass" @change="persist(device)">
            <option :value="null">— profile —</option>
            <option v-for="p in profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
          <select v-model="device.method" :class="inputClass" @change="persist(device)">
            <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
          </select>
          <select
            v-if="device.method === 'serial'"
            v-model.number="device.baudrate"
            :class="inputClass"
            @change="persist(device)"
          >
            <option v-for="b in BAUDRATES" :key="b" :value="b">{{ b }}</option>
          </select>
          <input
            v-if="device.method === 'can'"
            v-model="device.interface"
            :class="['w-20 font-mono', inputClass]"
            @change="persist(device)"
          />
          <label class="flex items-center gap-1 text-[10px]">
            <input v-model="device.exclude_from_batch" type="checkbox" @change="persist(device)" />
            exclude
          </label>
        </div>

        <input
          v-model="device.notes"
          placeholder="notes (URLs, pinout…)"
          :class="['w-full', inputClass]"
          @change="persist(device)"
        />

        <div v-if="device.serial_id" class="flex items-center gap-1 text-[10px]">
          <span class="nb-badge shrink-0 bg-brand-cyan">serial id</span>
          <span class="min-w-0 flex-1 truncate font-mono opacity-60">{{ device.serial_id }}</span>
          <button
            class="nb-btn shrink-0 px-1.5 py-0 text-[9px]"
            @click="detach(device, 'serial_id')"
          >
            detach
          </button>
        </div>
        <div v-if="device.dfu_id" class="flex items-center gap-1 text-[10px]">
          <span class="nb-badge shrink-0 bg-brand-yellow">dfu id</span>
          <span class="min-w-0 flex-1 truncate font-mono opacity-60">{{ device.dfu_id }}</span>
          <button class="nb-btn shrink-0 px-1.5 py-0 text-[9px]" @click="detach(device, 'dfu_id')">
            detach
          </button>
        </div>
      </div>
      <p v-if="!devices.length" class="font-mono text-xs opacity-70">
        No saved devices yet — add one below.
      </p>

      <!-- Discovered, not yet saved -->
      <div v-if="unmanaged.length" class="space-y-1.5 border-t-2 border-ink pt-2">
        <span class="text-xs font-bold uppercase tracking-wide">Discovered</span>
        <div
          v-for="board in unmanaged"
          :key="board.id"
          class="rounded-brutal border-2 border-ink px-2 py-1"
        >
          <div class="flex items-center gap-2">
            <span class="min-w-0 flex-1 truncate font-bold">{{ board.name }}</span>
            <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">{{
              board.connection
            }}</span>
            <button
              class="nb-btn shrink-0 bg-brand-lime px-2 py-0.5 text-[10px]"
              @click="addBoard(board)"
            >
              add
            </button>
            <button
              v-if="devices.length"
              class="nb-btn shrink-0 px-2 py-0.5 text-[10px]"
              @click="attachFor = attachFor === board.id ? null : board.id"
            >
              attach
            </button>
          </div>
          <div v-if="attachFor === board.id" class="mt-1 flex flex-wrap gap-1">
            <button
              v-for="device in devices"
              :key="device.id"
              class="nb-btn px-2 py-0.5 text-[10px]"
              @click="attachToDevice(board, device.id)"
            >
              → {{ device.name }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
