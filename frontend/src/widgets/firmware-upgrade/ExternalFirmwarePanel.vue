<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  deleteExternal,
  downloadExternal,
  fetchBoards,
  fetchDevices,
  fetchExternal,
  flashExternal,
  updateExternalMeta,
  uploadExternal,
} from './api'
import type { Board, Device, ExternalFirmware } from './types'

const items = ref<ExternalFirmware[]>([])
const targets = ref<{ id: string; label: string }[]>([])
const error = ref<string | null>(null)
const log = ref('')
const activeName = ref<string | null>(null)
const busy = ref(false)

const METHODS = ['serial', 'can', 'dfu', 'make']
const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

/** Per-firmware flash target + katapult choice (keyed by name). Always populated
 *  in load() — never created during render (which would loop the renderer). */
const flashTo = reactive<Record<string, { device: string; katapult: boolean }>>({})

async function load(): Promise<void> {
  error.value = null
  try {
    const [ext, dev, brd] = await Promise.all([fetchExternal(), fetchDevices(), fetchBoards()])
    items.value = ext.firmware
    const devs = dev.devices.map((d: Device) => ({ id: d.id, label: `${d.name} (device)` }))
    const boards = brd.boards
      .filter((b: Board) => b.connection !== 'linux')
      .map((b: Board) => ({ id: b.id, label: `${b.name} (${b.connection})` }))
    const seen = new Set<string>()
    targets.value = [...devs, ...boards].filter((t) => !seen.has(t.id) && seen.add(t.id))
    // Seed a flash choice for every firmware so the template never mutates state.
    for (const fw of items.value) {
      if (!flashTo[fw.name])
        flashTo[fw.name] = { device: targets.value[0]?.id ?? '', katapult: true }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load external firmware'
  }
}

async function onUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  error.value = null
  const dot = file.name.lastIndexOf('.')
  const ext = dot >= 0 ? file.name.slice(dot + 1) : 'bin'
  const name = (dot >= 0 ? file.name.slice(0, dot) : file.name).replace(/[^A-Za-z0-9 _.-]/g, '_')
  try {
    await uploadExternal(name, ext, file)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Upload failed'
  } finally {
    input.value = ''
  }
}

async function persist(fw: ExternalFirmware): Promise<void> {
  error.value = null
  try {
    await updateExternalMeta(fw.name, {
      label: fw.label,
      method: fw.method,
      offset: fw.offset,
      interface: fw.interface,
      notes: fw.notes,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Save failed'
  }
}

async function remove(fw: ExternalFirmware): Promise<void> {
  try {
    await deleteExternal(fw.name)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Delete failed'
  }
}

async function doFlash(fw: ExternalFirmware): Promise<void> {
  const target = flashTo[fw.name]
  if (busy.value || !target?.device) return
  error.value = null
  activeName.value = fw.name
  log.value = `>>> flashing ${fw.filename} → ${target.device}\n`
  busy.value = true
  try {
    await flashExternal(fw.name, target.device, target.katapult, (chunk) => {
      log.value += chunk
    })
  } catch (e) {
    log.value += `\n!! ${e instanceof Error ? e.message : 'flash failed'}\n`
  } finally {
    busy.value = false
  }
}

function kb(size: number): string {
  return size >= 1024 ? `${(size / 1024).toFixed(0)} KB` : `${size} B`
}

onMounted(load)
</script>

<template>
  <div class="space-y-1.5 border-t-2 border-ink pt-2">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">External firmware</span>
      <label class="nb-btn cursor-pointer px-2 py-0.5 text-[10px]">
        + upload .bin
        <input type="file" accept=".bin,.uf2,.elf,.hex" class="hidden" @change="onUpload" />
      </label>
    </div>
    <p class="font-mono text-[10px] opacity-60">
      Flash a pre-built firmware file as-is (no build). Set how each is flashed, then pick a board.
    </p>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <div
      v-for="fw in items"
      :key="fw.name"
      class="space-y-1.5 rounded-brutal border-2 border-ink p-2"
    >
      <div class="flex items-center gap-2">
        <input
          v-model="fw.label"
          :class="['min-w-0 flex-1 font-bold', inputClass]"
          @change="persist(fw)"
        />
        <span class="shrink-0 font-mono text-[9px] opacity-50"
          >{{ fw.filename }} · {{ kb(fw.size) }}</span
        >
        <button class="nb-btn shrink-0 px-2 py-0.5 text-[10px]" @click="downloadExternal(fw.name)">
          ↓
        </button>
        <button
          class="nb-btn shrink-0 bg-brand-red px-2 py-0.5 text-[10px] text-surface"
          @click="remove(fw)"
        >
          remove
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <select v-model="fw.method" :class="inputClass" @change="persist(fw)">
          <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
        </select>
        <input
          v-model="fw.offset"
          placeholder="offset (DFU, e.g. 0x08002000)"
          :class="['w-44 font-mono', inputClass]"
          @change="persist(fw)"
        />
        <input
          v-if="fw.method === 'can'"
          v-model="fw.interface"
          :class="['w-20 font-mono', inputClass]"
          @change="persist(fw)"
        />
      </div>
      <input
        v-model="fw.notes"
        placeholder="notes (source, board, version…)"
        :class="['w-full', inputClass]"
        @change="persist(fw)"
      />

      <div
        v-if="flashTo[fw.name]"
        class="flex flex-wrap items-center gap-1.5 border-t-2 border-dashed border-ink pt-1.5"
      >
        <span class="text-[10px] opacity-60">flash to:</span>
        <select v-model="flashTo[fw.name].device" :class="inputClass">
          <option v-for="t in targets" :key="t.id" :value="t.id">{{ t.label }}</option>
        </select>
        <label class="flex items-center gap-1 text-[10px]">
          <input v-model="flashTo[fw.name].katapult" type="checkbox" /> katapult
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-[10px] text-surface"
          :disabled="busy || !flashTo[fw.name].device"
          @click="doFlash(fw)"
        >
          {{ busy && activeName === fw.name ? 'flashing…' : 'flash' }}
        </button>
      </div>

      <pre
        v-if="log && activeName === fw.name"
        class="max-h-40 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight text-surface"
        >{{ log }}</pre
      >
    </div>

    <p v-if="!items.length" class="font-mono text-xs opacity-70">
      No external firmware yet — upload a .bin to flash it directly.
    </p>
  </div>
</template>
