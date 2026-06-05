<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  attachIdentity,
  exportBackup,
  fetchBoards,
  fetchDevices,
  fetchProfiles,
  importBackup,
  removeDevice,
  saveDevice,
} from './api'
import type { Board, Device, FirmwareProfile } from './types'

defineEmits<{ close: [] }>()

const { t } = useI18n({ useScope: 'global' })

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

/** Boards on the bus that are not yet saved in the registry (the host MCU is
 *  managed separately, so it never appears as an addable board). */
const unmanaged = computed(() => boards.value.filter((b) => !b.managed && b.connection !== 'linux'))

/** Short bootloader / run-mode label for a discovered board (e.g. KATAPULT, DFU). */
function boardBadge(board: Board): string {
  return (board.application || board.mode || '').toUpperCase()
}

/** Live bus mode (service / ready / dfu / …) keyed by board id. */
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
    error.value = e instanceof Error ? e.message : t('firmware.devices.loadFailed')
  } finally {
    loading.value = false
  }
}

async function persist(device: Device): Promise<void> {
  error.value = null
  try {
    await saveDevice({ ...device })
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.devices.saveFailed')
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
    error.value = e instanceof Error ? e.message : t('firmware.devices.addFailed')
  }
}

async function attachToDevice(board: Board, deviceId: string): Promise<void> {
  error.value = null
  try {
    await attachIdentity(deviceId, board.id, board.connection === 'dfu' ? 'dfu' : 'serial')
    attachFor.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.devices.attachFailed')
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
    error.value = e instanceof Error ? e.message : t('firmware.devices.removeFailed')
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

// --- Backup & restore the registry + profiles ---
const backupMsg = ref<string | null>(null)

async function doExport(): Promise<void> {
  backupMsg.value = null
  error.value = null
  try {
    await exportBackup()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.devices.exportFailed')
  }
}

async function onImportFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  backupMsg.value = null
  error.value = null
  try {
    const summary = await importBackup(file)
    const extra = summary.restored_devices ? t('firmware.devices.restoredDevicesSuffix') : ''
    const n = summary.restored_profiles.length
    backupMsg.value = t('firmware.devices.restored', { n, extra }, n)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.devices.importFailed')
  } finally {
    input.value = ''
  }
}

onMounted(() => {
  void load()
  boardsTimer = setInterval(refreshBoards, 6000)
})

onUnmounted(() => {
  if (boardsTimer) clearInterval(boardsTimer)
})
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">{{
        t('firmware.devices.title')
      }}</span>
      <button class="nb-btn px-2 py-0.5 text-xs" @click="$emit('close')">
        {{ t('firmware.devices.back') }}
      </button>
    </div>
    <p class="font-mono text-[10px] opacity-60">
      {{ t('firmware.devices.intro') }}
    </p>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
    <div v-if="loading" class="font-mono text-xs">{{ t('firmware.devices.loading') }}</div>

    <template v-else>
      <!-- Registered devices (configure each board) -->
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
          <button
            class="nb-btn shrink-0 bg-brand-red px-2 py-0.5 text-[10px] text-surface"
            @click="remove(device)"
          >
            {{ t('firmware.devices.remove') }}
          </button>
        </div>
        <div class="font-mono text-[9px] opacity-50">{{ device.id }}</div>

        <div class="flex flex-wrap items-center gap-1.5">
          <select v-model="device.profile" :class="inputClass" @change="persist(device)">
            <option :value="null">{{ t('firmware.devices.profilePlaceholder') }}</option>
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
          <label
            v-if="device.method === 'serial' || device.method === 'can'"
            class="flex items-center gap-1 text-[10px]"
            :title="t('firmware.devices.katapultHint')"
          >
            <input v-model="device.is_katapult" type="checkbox" @change="persist(device)" />
            {{ t('firmware.devices.katapult') }}
          </label>
          <label class="flex items-center gap-1 text-[10px]">
            <input v-model="device.exclude_from_batch" type="checkbox" @change="persist(device)" />
            {{ t('firmware.devices.exclude') }}
          </label>
        </div>

        <input
          v-model="device.notes"
          :placeholder="t('firmware.devices.notesPlaceholder')"
          :class="['w-full', inputClass]"
          @change="persist(device)"
        />

        <!-- Linked bootloader identities — a board enumerates under a separate id
             when it drops into Katapult / DFU; show each as a connected sub-card. -->
        <div
          v-if="device.serial_id"
          class="ms-3 flex items-center gap-2 rounded-brutal border-2 border-ink bg-surface px-2 py-1 text-[10px]"
        >
          <span class="nb-badge shrink-0 bg-brand-cyan text-[9px]">{{
            t('firmware.devices.serialIdentity')
          }}</span>
          <span class="min-w-0 flex-1 truncate font-mono opacity-60">{{ device.serial_id }}</span>
          <button
            class="nb-btn shrink-0 px-1.5 py-0 text-[9px]"
            @click="detach(device, 'serial_id')"
          >
            {{ t('firmware.devices.unlink') }}
          </button>
        </div>
        <div
          v-if="device.dfu_id"
          class="ms-3 flex items-center gap-2 rounded-brutal border-2 border-ink bg-surface px-2 py-1 text-[10px]"
        >
          <span class="nb-badge shrink-0 bg-brand-yellow text-[9px]">{{
            t('firmware.devices.dfuIdentity')
          }}</span>
          <span class="min-w-0 flex-1 truncate font-mono opacity-60">{{ device.dfu_id }}</span>
          <button class="nb-btn shrink-0 px-1.5 py-0 text-[9px]" @click="detach(device, 'dfu_id')">
            {{ t('firmware.devices.unlink') }}
          </button>
        </div>
      </div>
      <p v-if="!devices.length" class="font-mono text-xs opacity-70">
        {{ t('firmware.devices.empty') }}
      </p>

      <!-- Discovered, not yet saved -->
      <div v-if="unmanaged.length" class="space-y-1.5 border-t-2 border-ink pt-2">
        <span class="text-xs font-bold uppercase tracking-wide">{{
          t('firmware.devices.discovered')
        }}</span>
        <div
          v-for="board in unmanaged"
          :key="board.id"
          class="rounded-brutal border-2 border-ink px-2 py-1"
        >
          <div class="flex items-center gap-2">
            <span class="min-w-0 flex-1 truncate font-bold">{{ board.name }}</span>
            <span
              v-if="boardBadge(board)"
              class="nb-badge shrink-0 text-[9px]"
              :class="modeClass(board.mode)"
            >
              {{ boardBadge(board) }}
            </span>
            <span class="shrink-0 font-mono text-[9px] uppercase opacity-50">{{
              board.connection
            }}</span>
            <button
              class="nb-btn shrink-0 bg-brand-lime px-2 py-0.5 text-[10px]"
              @click="addBoard(board)"
            >
              {{ t('firmware.devices.add') }}
            </button>
            <button
              v-if="devices.length"
              class="nb-btn shrink-0 px-2 py-0.5 text-[10px]"
              :title="t('firmware.devices.linkHint')"
              @click="attachFor = attachFor === board.id ? null : board.id"
            >
              {{ t('firmware.devices.link') }}
            </button>
          </div>
          <div v-if="attachFor === board.id" class="mt-1 flex flex-wrap items-center gap-1">
            <span class="text-[10px] opacity-60">{{ t('firmware.devices.linkTo') }}</span>
            <button
              v-for="device in devices"
              :key="device.id"
              class="nb-btn px-2 py-0.5 text-[10px]"
              @click="attachToDevice(board, device.id)"
            >
              {{ t('firmware.devices.linkTarget', { name: device.name }) }}
            </button>
          </div>
        </div>
      </div>

      <!-- Backup & restore the registry + profiles -->
      <div class="space-y-1.5 border-t-2 border-ink pt-2">
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs font-bold uppercase tracking-wide">{{
            t('firmware.devices.backup')
          }}</span>
          <div class="flex gap-1">
            <button class="nb-btn px-2 py-0.5 text-[10px]" @click="doExport">
              {{ t('firmware.devices.export') }}
            </button>
            <label class="nb-btn cursor-pointer px-2 py-0.5 text-[10px]">
              {{ t('firmware.devices.import') }}
              <input type="file" accept=".zip" class="hidden" @change="onImportFile" />
            </label>
          </div>
        </div>
        <p v-if="backupMsg" class="font-mono text-[10px] opacity-70">{{ backupMsg }}</p>
      </div>
    </template>
  </div>
</template>
