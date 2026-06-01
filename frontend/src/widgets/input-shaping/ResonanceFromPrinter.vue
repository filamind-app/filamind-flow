<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { analyzeResonanceFile, listResonanceFiles, runLiveTest } from './api'
import type { ResonanceFile, ShaperAnalysis } from './types'

const emit = defineEmits<{ analyzed: [ShaperAnalysis] }>()

const files = ref<ResonanceFile[]>([])
const dirs = ref<string[]>([])
const error = ref<string | null>(null)
const busy = ref(false)
const liveAxis = ref<'x' | 'y'>('x')
const liveReady = ref(false)
const liveBusy = ref(false)

const inputClass = 'rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

function msg(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

function kb(size: number): string {
  return size >= 1024 ? `${(size / 1024).toFixed(0)} KB` : `${size} B`
}

async function loadFiles(): Promise<void> {
  error.value = null
  try {
    const r = await listResonanceFiles()
    files.value = r.files
    dirs.value = r.dirs
  } catch (e) {
    error.value = msg(e, 'Could not list printer files')
  }
}

async function importFile(f: ResonanceFile): Promise<void> {
  if (busy.value) return
  error.value = null
  busy.value = true
  try {
    emit('analyzed', await analyzeResonanceFile(f.path, f.axis ?? undefined))
  } catch (e) {
    error.value = msg(e, 'Analysis failed')
  } finally {
    busy.value = false
  }
}

async function live(): Promise<void> {
  if (liveBusy.value || !liveReady.value) return
  error.value = null
  liveBusy.value = true
  try {
    const result = await runLiveTest(liveAxis.value)
    liveReady.value = false
    emit('analyzed', result)
    await loadFiles()
  } catch (e) {
    error.value = msg(e, 'Live test failed')
  } finally {
    liveBusy.value = false
  }
}

onMounted(loadFiles)
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2">
    <div class="flex items-center justify-between">
      <span class="text-xs font-bold uppercase tracking-wide">From the printer</span>
      <button class="nb-btn px-2 py-0.5 text-[10px]" @click="loadFiles">↻ refresh</button>
    </div>

    <!-- Live test: moves the toolhead, so it is gated behind a confirm checkbox. -->
    <div class="space-y-1 rounded-brutal border-2 border-dashed border-ink p-2">
      <div class="flex flex-wrap items-center gap-2 text-[10px]">
        <span class="font-bold">🔴 Live test</span>
        <select v-model="liveAxis" :class="inputClass">
          <option value="x">axis X</option>
          <option value="y">axis Y</option>
        </select>
        <label class="flex items-center gap-1">
          <input v-model="liveReady" type="checkbox" /> ⚠ moves the toolhead — I'm ready
        </label>
        <button
          class="nb-btn bg-brand-red px-2 py-0.5 text-surface"
          :disabled="!liveReady || liveBusy"
          @click="live"
        >
          {{ liveBusy ? 'running…' : 'run TEST_RESONANCES' }}
        </button>
      </div>
      <p class="font-mono text-[9px] opacity-60">
        Runs TEST_RESONANCES on the printer (needs an accelerometer + a
        <code>[resonance_tester]</code>). Refused while printing.
      </p>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <!-- Resonance CSVs already on the host. -->
    <p v-if="!files.length" class="font-mono text-[10px] opacity-60">
      No resonance CSVs found{{ dirs.length ? ` in ${dirs.join(', ')}` : '' }}.
    </p>
    <div v-for="f in files" :key="f.path" class="flex items-center gap-2 font-mono text-[10px]">
      <span v-if="f.axis" class="nb-badge shrink-0 bg-brand-cyan">{{ f.axis.toUpperCase() }}</span>
      <span class="min-w-0 flex-1 truncate">{{ f.name }}</span>
      <span class="shrink-0 opacity-50">{{ kb(f.size) }}</span>
      <button class="nb-btn shrink-0 px-2 py-0.5" :disabled="busy" @click="importFile(f)">
        analyze
      </button>
    </div>
  </div>
</template>
