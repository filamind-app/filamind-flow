<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import FirmwareConfigEditor from './FirmwareConfigEditor.vue'
import { fetchBoards, fetchFirmwareStatus } from './api'
import type { BoardDiscovery, FirmwareStatus, FirmwareTools } from './types'

const mode = ref<'status' | 'configure'>('status')
const status = ref<FirmwareStatus | null>(null)
const boards = ref<BoardDiscovery | null>(null)
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

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [statusData, boardsData] = await Promise.all([fetchFirmwareStatus(), fetchBoards()])
    status.value = statusData
    boards.value = boardsData
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load firmware status'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-3 text-sm">
    <FirmwareConfigEditor v-if="mode === 'configure'" @close="mode = 'status'" />
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
            class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink px-2 py-1"
          >
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

          <p v-if="!status.mcus.length" class="font-mono text-xs opacity-70">
            {{ status.reachable ? 'No MCUs reported.' : 'Printer not reachable.' }}
          </p>
        </div>

        <div class="flex items-center justify-between gap-2 border-t-2 border-ink pt-2 text-xs">
          <span class="font-bold">Linux host MCU</span>
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
            <span v-if="board.configured" class="nb-badge shrink-0 bg-surface text-[9px]">cfg</span>
            <span class="nb-badge shrink-0" :class="boardModeClass(board.mode)">{{
              board.mode
            }}</span>
          </div>
          <p v-if="!boards.boards.length" class="font-mono text-xs opacity-70">
            No flashable boards detected.
          </p>
        </div>

        <button class="nb-btn w-full bg-brand-cyan py-1 text-xs" @click="mode = 'configure'">
          Configure firmware →
        </button>
      </template>
    </template>
  </div>
</template>
