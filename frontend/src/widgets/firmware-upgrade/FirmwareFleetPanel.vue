<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  attachIdentity,
  fetchBoards,
  fetchFleet,
  fetchProfiles,
  removeFleetDevice,
  saveFleetDevice,
} from './api'
import type { Board, FirmwareProfile, FleetDevice } from './types'

defineEmits<{ close: [] }>()

const fleet = ref<FleetDevice[]>([])
const boards = ref<Board[]>([])
const profiles = ref<FirmwareProfile[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
/** Id of the discovered board currently choosing a fleet device to attach to. */
const attachFor = ref<string | null>(null)

const METHODS = ['serial', 'can', 'dfu', 'linux']
const BAUDRATES = [115200, 230400, 250000, 500000, 1000000]
const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

/** Boards on the bus that are not yet saved in the fleet. */
const unmanaged = computed(() => boards.value.filter((b) => !b.managed))

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [fleetData, boardData, profileData] = await Promise.all([
      fetchFleet(),
      fetchBoards(),
      fetchProfiles(),
    ])
    fleet.value = fleetData.devices
    boards.value = boardData.boards
    profiles.value = profileData.profiles
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load fleet'
  } finally {
    loading.value = false
  }
}

async function persist(device: FleetDevice): Promise<void> {
  error.value = null
  try {
    await saveFleetDevice({ ...device })
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
    await saveFleetDevice({
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

async function attachToDevice(board: Board, fleetId: string): Promise<void> {
  error.value = null
  try {
    await attachIdentity(fleetId, board.id, board.connection === 'dfu' ? 'dfu' : 'serial')
    attachFor.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Attach failed'
  }
}

async function detach(device: FleetDevice, field: 'serial_id' | 'dfu_id'): Promise<void> {
  device[field] = null
  await persist(device)
}

async function remove(device: FleetDevice): Promise<void> {
  error.value = null
  try {
    await removeFleetDevice(device.id)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Remove failed'
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">Fleet</span>
      <button class="nb-btn px-2 py-0.5 text-xs" @click="$emit('close')">← back</button>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
    <div v-if="loading" class="font-mono text-xs">Loading fleet…</div>

    <template v-else>
      <!-- Registered fleet -->
      <div
        v-for="device in fleet"
        :key="device.id"
        class="space-y-1.5 rounded-brutal border-2 border-ink p-2"
      >
        <div class="flex items-center gap-2">
          <input
            v-model="device.name"
            :class="['min-w-0 flex-1 font-bold', inputClass]"
            @change="persist(device)"
          />
          <span v-if="device.flashed_version" class="shrink-0 font-mono text-[9px] opacity-60">{{
            device.flashed_version
          }}</span>
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
      <p v-if="!fleet.length" class="font-mono text-xs opacity-70">
        No boards in the fleet yet — add one below.
      </p>

      <!-- Discovered, not yet in the fleet -->
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
              v-if="fleet.length"
              class="nb-btn shrink-0 px-2 py-0.5 text-[10px]"
              @click="attachFor = attachFor === board.id ? null : board.id"
            >
              attach
            </button>
          </div>
          <div v-if="attachFor === board.id" class="mt-1 flex flex-wrap gap-1">
            <button
              v-for="device in fleet"
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
