<script setup lang="ts">
/** One place to choose the resonance CSV to analyse: an EXTERNAL upload, or a LOCAL
 *  file on the printer host (the scanned resonance dirs + the persistent archive). It
 *  only picks/lists + manages the archive; it emits `analyze` and lets the parent run
 *  the analysis (so the advanced params + the shared result/history stay in one place).
 */
import { onMounted, ref } from 'vue'

import {
  deleteArchiveRun,
  downloadArchiveFile,
  listArchive,
  listResonanceFiles,
  saveFileToArchive,
} from './api'
import HelpNote from './HelpNote.vue'
import type { ArchiveRun, ResonanceFile } from './types'

const props = defineProps<{ busy: boolean }>()
const emit = defineEmits<{
  analyze: [{ kind: 'upload' | 'host'; file?: File; path?: string; axis: string | null }]
}>()

const source = ref<'upload' | 'host'>('upload')
const file = ref<File | null>(null)
const axis = ref<'auto' | 'x' | 'y'>('auto')

const files = ref<ResonanceFile[]>([])
const dirs = ref<string[]>([])
const runs = ref<ArchiveRun[]>([])
const error = ref<string | null>(null)
const working = ref(false)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

function tabClass(s: 'upload' | 'host'): string {
  return source.value === s ? 'bg-brand-cyan ring-2 ring-ink' : ''
}
function kb(size: number): string {
  return size >= 1024 ? `${(size / 1024).toFixed(0)} KB` : `${size} B`
}
function msg(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}
function fmtDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function onPick(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function loadHost(): Promise<void> {
  try {
    const r = await listResonanceFiles()
    files.value = r.files
    dirs.value = r.dirs
  } catch (e) {
    error.value = msg(e, 'Could not list printer files')
  }
}
async function loadArchive(): Promise<void> {
  try {
    runs.value = (await listArchive()).runs
  } catch (e) {
    error.value = msg(e, 'Could not list the archive')
  }
}
async function refresh(): Promise<void> {
  error.value = null
  await Promise.all([loadHost(), loadArchive()])
}

function analyzeUpload(): void {
  if (!file.value || props.busy) return
  emit('analyze', {
    kind: 'upload',
    file: file.value,
    axis: axis.value === 'auto' ? null : axis.value,
  })
}
function analyzeHost(f: ResonanceFile): void {
  if (props.busy) return
  emit('analyze', { kind: 'host', path: f.path, axis: f.axis })
}

async function saveHostToArchive(f: ResonanceFile): Promise<void> {
  if (working.value) return
  error.value = null
  working.value = true
  try {
    await saveFileToArchive(f.path, 'shaper', f.axis)
    await loadArchive()
  } catch (e) {
    error.value = msg(e, 'Save to archive failed')
  } finally {
    working.value = false
  }
}
async function removeRun(run: ArchiveRun): Promise<void> {
  if (working.value) return
  error.value = null
  working.value = true
  try {
    await deleteArchiveRun(run.id)
    runs.value = runs.value.filter((r) => r.id !== run.id)
  } catch (e) {
    error.value = msg(e, 'Delete failed')
  } finally {
    working.value = false
  }
}
async function download(run: ArchiveRun, filename: string): Promise<void> {
  error.value = null
  try {
    await downloadArchiveFile(run.id, filename)
  } catch (e) {
    error.value = msg(e, 'Download failed')
  }
}

onMounted(refresh)
defineExpose({ refresh })
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide">CSV source</span>
      <button
        class="nb-btn px-2 py-0.5 text-[10px]"
        :class="tabClass('upload')"
        @click="source = 'upload'"
      >
        📤 Upload
      </button>
      <button
        class="nb-btn px-2 py-0.5 text-[10px]"
        :class="tabClass('host')"
        @click="source = 'host'"
      >
        🖥 From printer
      </button>
      <HelpNote topic="analyze" />
    </div>

    <!-- External upload -->
    <div v-if="source === 'upload'" class="flex flex-wrap items-center gap-2">
      <label class="nb-btn cursor-pointer px-2 py-1 text-xs">
        📈 Select CSV
        <input type="file" accept=".csv" class="hidden" @change="onPick" />
      </label>
      <select v-model="axis" :class="inputClass" title="Axis this data belongs to">
        <option value="auto">axis: auto</option>
        <option value="x">axis: X</option>
        <option value="y">axis: Y</option>
      </select>
      <button
        class="nb-btn bg-brand-lime px-3 py-1 text-xs"
        :disabled="!file || busy"
        @click="analyzeUpload"
      >
        {{ busy ? 'Analyzing…' : '🚀 Analyze' }}
      </button>
      <span v-if="file" class="min-w-0 truncate font-mono text-[10px] opacity-60">{{
        file.name
      }}</span>
    </div>

    <!-- Local: host scan dirs + the persistent archive -->
    <div v-else class="space-y-2">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[9px] opacity-60">on the printer host</span>
        <button class="nb-btn px-2 py-0.5 text-[10px]" @click="refresh">↻ refresh</button>
      </div>

      <p v-if="!files.length" class="font-mono text-[10px] opacity-60">
        No resonance CSVs found{{ dirs.length ? ` in ${dirs.join(', ')}` : '' }}.
      </p>
      <div v-for="f in files" :key="f.path" class="flex items-center gap-2 font-mono text-[10px]">
        <span v-if="f.axis" class="nb-badge shrink-0 bg-brand-cyan">{{
          f.axis.toUpperCase()
        }}</span>
        <span class="min-w-0 flex-1 truncate">{{ f.name }}</span>
        <span class="shrink-0 opacity-50">{{ kb(f.size) }}</span>
        <button class="nb-btn shrink-0 px-2 py-0.5" :disabled="busy" @click="analyzeHost(f)">
          analyze
        </button>
        <button
          class="nb-btn shrink-0 px-2 py-0.5"
          :disabled="working"
          title="Copy this capture into the archive"
          @click="saveHostToArchive(f)"
        >
          💾 save
        </button>
      </div>

      <!-- Persistent archive: saved captures + generated configs. -->
      <div class="space-y-1 border-t-2 border-ink pt-2">
        <span class="text-[10px] font-bold uppercase tracking-wide">Archive</span>
        <p v-if="!runs.length" class="font-mono text-[10px] opacity-60">
          Nothing saved yet — use 💾 save above, or "save to archive" under a config.
        </p>
        <div
          v-for="run in runs"
          :key="run.id"
          class="flex flex-wrap items-center gap-2 font-mono text-[9px]"
        >
          <span class="nb-badge shrink-0 bg-brand-yellow">{{ run.kind }}</span>
          <span v-if="run.axis" class="nb-badge shrink-0 bg-brand-cyan">{{
            run.axis.toUpperCase()
          }}</span>
          <span class="shrink-0 opacity-60">{{ fmtDate(run.at) }}</span>
          <span class="min-w-0 flex-1 truncate opacity-70">{{ run.files.join(', ') }}</span>
          <span class="shrink-0 opacity-50">{{ kb(run.size) }}</span>
          <button
            v-for="fn in run.files"
            :key="fn"
            class="nb-btn shrink-0 px-1.5 py-0.5"
            :title="`download ${fn}`"
            @click="download(run, fn)"
          >
            ⬇ {{ fn.endsWith('.cfg') ? 'cfg' : 'csv' }}
          </button>
          <button
            class="nb-btn shrink-0 bg-brand-red px-1.5 py-0.5 text-surface"
            :disabled="working"
            @click="removeRun(run)"
          >
            🗑
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
  </div>
</template>
