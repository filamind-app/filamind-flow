<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

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
import { compareFirmware, type DiffRow, type DiffStatus } from './compare'
import type { Board, Device, ExternalFirmware } from './types'

const { t } = useI18n({ useScope: 'global' })

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

/** Which firmware rows have their baked-in config expanded (toggled in a handler). */
const expanded = reactive<Record<string, boolean>>({})

/** A firmware's baked-in config as sorted [key, value] pairs. */
function configEntries(fw: ExternalFirmware): [string, string][] {
  return Object.entries(fw.detected_config ?? {}).sort((a, b) => a[0].localeCompare(b[0]))
}

/** Two files chosen for the A ⇄ B comparison (by name; null = unset). */
const compareA = ref<string | null>(null)
const compareB = ref<string | null>(null)

/** The diff of the two chosen files, or null until two *distinct* files are picked. */
const comparison = computed(() => {
  if (!compareA.value || !compareB.value || compareA.value === compareB.value) return null
  const a = items.value.find((f) => f.name === compareA.value)
  const b = items.value.find((f) => f.name === compareB.value)
  return a && b ? compareFirmware(a, b) : null
})

function clearCompare(): void {
  compareA.value = null
  compareB.value = null
}

/** A chosen file's display label, for the comparison column headers. */
function fwLabel(name: string | null): string {
  const fw = items.value.find((f) => f.name === name)
  return fw ? fw.label || fw.name : ''
}

/** A diff-row status → its Neo-Brutalist row tint. */
function rowClass(status: DiffStatus): string {
  return {
    same: 'opacity-50',
    changed: 'rounded bg-brand-yellow/40 px-1',
    a_only: 'rounded bg-brand-red/20 px-1',
    b_only: 'rounded bg-brand-lime/50 px-1',
  }[status]
}

/** One side of a diff row, formatting the size field as KB. */
function cell(row: DiffRow, side: 'a' | 'b'): string {
  const value = side === 'a' ? row.a : row.b
  if (value === null) return '—'
  return row.key === 'size' ? kb(Number(value)) : value
}

async function load(): Promise<void> {
  error.value = null
  try {
    const [ext, dev, brd] = await Promise.all([fetchExternal(), fetchDevices(), fetchBoards()])
    items.value = ext.firmware
    // Drop a comparison pick whose file was removed.
    const names = new Set(items.value.map((f) => f.name))
    if (compareA.value && !names.has(compareA.value)) compareA.value = null
    if (compareB.value && !names.has(compareB.value)) compareB.value = null
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
    error.value = e instanceof Error ? e.message : t('firmware.external.loadFailed')
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
    error.value = e instanceof Error ? e.message : t('firmware.external.uploadFailed')
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
    error.value = e instanceof Error ? e.message : t('firmware.external.saveFailed')
  }
}

async function remove(fw: ExternalFirmware): Promise<void> {
  try {
    await deleteExternal(fw.name)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.external.deleteFailed')
  }
}

async function doFlash(fw: ExternalFirmware): Promise<void> {
  const target = flashTo[fw.name]
  if (busy.value || !target?.device) return
  error.value = null
  activeName.value = fw.name
  log.value = `>>> ${t('firmware.external.flashingLog', { filename: fw.filename, device: target.device })}\n`
  busy.value = true
  try {
    await flashExternal(fw.name, target.device, target.katapult, (chunk) => {
      log.value += chunk
    })
  } catch (e) {
    log.value += `\n!! ${e instanceof Error ? e.message : t('firmware.external.flashFailed')}\n`
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
      <span class="text-xs font-bold uppercase tracking-wide">{{
        t('firmware.external.title')
      }}</span>
      <label class="nb-btn cursor-pointer px-2 py-0.5 text-[11px]">
        {{ t('firmware.external.upload') }}
        <input type="file" accept=".bin,.uf2,.elf,.hex" class="hidden" @change="onUpload" />
      </label>
    </div>
    <p class="font-mono text-[11px] opacity-60">
      {{ t('firmware.external.intro') }}
    </p>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <!-- Compare two files: an A ⇄ B diff of their detected properties (read-only). -->
    <div
      v-if="items.length >= 2"
      class="space-y-1.5 rounded-brutal border-2 border-ink bg-paper p-2"
    >
      <div class="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span class="font-bold uppercase tracking-wide">{{ t('firmware.external.compare') }}</span>
        <select v-model="compareA" :class="inputClass">
          <option :value="null">{{ t('firmware.external.optionA') }}</option>
          <option v-for="fw in items" :key="fw.name" :value="fw.name">
            {{ fw.label || fw.name }}
          </option>
        </select>
        <span class="font-bold">⇄</span>
        <select v-model="compareB" :class="inputClass">
          <option :value="null">{{ t('firmware.external.optionB') }}</option>
          <option v-for="fw in items" :key="fw.name" :value="fw.name">
            {{ fw.label || fw.name }}
          </option>
        </select>
        <button
          v-if="compareA || compareB"
          class="nb-btn px-1.5 py-0 text-[10px]"
          @click="clearCompare"
        >
          {{ t('firmware.external.clear') }}
        </button>
      </div>

      <div
        v-if="compareA && compareB && compareA === compareB"
        class="font-mono text-[10px] opacity-60"
      >
        {{ t('firmware.external.pickTwoDifferent') }}
      </div>

      <div v-else-if="comparison" class="space-y-1">
        <div class="flex flex-wrap gap-1 font-mono text-[10px]">
          <span class="nb-badge bg-brand-yellow">{{
            t('firmware.external.countChanged', { n: comparison.counts.changed })
          }}</span>
          <span class="nb-badge bg-brand-red text-surface">{{
            t('firmware.external.countOnlyA', { n: comparison.counts.a_only })
          }}</span>
          <span class="nb-badge bg-brand-lime">{{
            t('firmware.external.countOnlyB', { n: comparison.counts.b_only })
          }}</span>
          <span class="nb-badge">{{
            t('firmware.external.countSame', { n: comparison.counts.same })
          }}</span>
        </div>

        <div
          class="grid grid-cols-[6rem_1fr_1fr] gap-2 border-b-2 border-ink pb-0.5 font-mono text-[10px] font-bold"
        >
          <span></span>
          <span class="min-w-0 truncate">{{
            t('firmware.external.headerA', { label: fwLabel(compareA) })
          }}</span>
          <span class="min-w-0 truncate">{{
            t('firmware.external.headerB', { label: fwLabel(compareB) })
          }}</span>
        </div>

        <div
          v-for="row in comparison.meta"
          :key="'m-' + row.key"
          class="grid grid-cols-[6rem_1fr_1fr] items-center gap-2 font-mono text-[10px]"
          :class="rowClass(row.status)"
        >
          <span class="opacity-70">{{ row.key }}</span>
          <span class="min-w-0 break-all">{{ cell(row, 'a') }}</span>
          <span class="min-w-0 break-all">{{ cell(row, 'b') }}</span>
        </div>

        <div v-if="comparison.config.length" class="mt-0.5 space-y-px border-t-2 border-ink pt-0.5">
          <div
            v-for="row in comparison.config"
            :key="'c-' + row.key"
            class="grid grid-cols-[6rem_1fr_1fr] items-center gap-2 font-mono text-[10px]"
            :class="rowClass(row.status)"
          >
            <span class="min-w-0 break-all opacity-70">{{ row.key }}</span>
            <span class="min-w-0 break-all">{{ cell(row, 'a') }}</span>
            <span class="min-w-0 break-all">{{ cell(row, 'b') }}</span>
          </div>
        </div>

        <p class="pt-0.5 text-[8px] italic opacity-50">
          {{ t('firmware.external.compareNote') }}
        </p>
      </div>
    </div>

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
        <span class="shrink-0 font-mono text-[10px] opacity-50"
          >{{ fw.filename }} · {{ kb(fw.size) }}</span
        >
        <button class="nb-btn shrink-0 px-2 py-0.5 text-[11px]" @click="downloadExternal(fw.name)">
          ↓
        </button>
        <button
          class="nb-btn shrink-0 bg-brand-red px-2 py-0.5 text-[11px] text-surface"
          @click="remove(fw)"
        >
          {{ t('firmware.external.remove') }}
        </button>
      </div>

      <!-- Read-only properties baked into the firmware (from its data dictionary). -->
      <div
        v-if="fw.detected_version || fw.detected_mcu || fw.detected_config"
        class="rounded-brutal border-2 border-ink bg-paper px-2 py-1"
      >
        <div class="flex flex-wrap items-center gap-x-2 font-mono text-[10px] opacity-70">
          <span>{{ t('firmware.external.readFromFile') }}</span>
          <span v-if="fw.detected_app" class="font-bold">{{ fw.detected_app }}</span>
          <span v-if="fw.detected_version">{{ fw.detected_version }}</span>
          <span v-if="fw.detected_mcu">{{
            t('firmware.external.mcuLabel', { mcu: fw.detected_mcu })
          }}</span>
          <button
            v-if="configEntries(fw).length"
            class="nb-btn ms-auto px-1.5 py-0 text-[10px]"
            @click="expanded[fw.name] = !expanded[fw.name]"
          >
            {{ expanded[fw.name] ? t('firmware.external.hide') : t('firmware.external.config') }}
            ({{ configEntries(fw).length }})
          </button>
        </div>
        <div v-if="expanded[fw.name]" class="mt-1 space-y-0.5">
          <div
            v-for="[k, v] in configEntries(fw)"
            :key="k"
            class="flex justify-between gap-2 font-mono text-[10px]"
          >
            <span class="opacity-70">{{ k }}</span>
            <span class="min-w-0 truncate">{{ v }}</span>
          </div>
          <p class="pt-0.5 text-[8px] italic opacity-50">
            {{ t('firmware.external.compiledNote') }}
          </p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <select v-model="fw.method" :class="inputClass" @change="persist(fw)">
          <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
        </select>
        <input
          v-model="fw.offset"
          :placeholder="t('firmware.external.offsetPlaceholder')"
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
        :placeholder="t('firmware.external.notesPlaceholder')"
        :class="['w-full', inputClass]"
        @change="persist(fw)"
      />

      <div
        v-if="flashTo[fw.name]"
        class="flex flex-wrap items-center gap-1.5 border-t-2 border-ink pt-1.5"
      >
        <span class="text-[11px] opacity-60">{{ t('firmware.external.flashTo') }}</span>
        <select v-model="flashTo[fw.name].device" :class="inputClass">
          <option v-for="tgt in targets" :key="tgt.id" :value="tgt.id">{{ tgt.label }}</option>
        </select>
        <label class="flex items-center gap-1 text-[11px]">
          <input v-model="flashTo[fw.name].katapult" type="checkbox" />
          {{ t('firmware.external.katapult') }}
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-[11px] text-surface"
          :disabled="busy || !flashTo[fw.name].device"
          @click="doFlash(fw)"
        >
          {{
            busy && activeName === fw.name
              ? t('firmware.external.flashing')
              : t('firmware.external.flash')
          }}
        </button>
      </div>

      <pre
        v-if="log && activeName === fw.name"
        class="max-h-40 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
        >{{ log }}</pre
      >
    </div>

    <p v-if="!items.length" class="font-mono text-xs opacity-70">
      {{ t('firmware.external.empty') }}
    </p>
  </div>
</template>
