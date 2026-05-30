<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchFirmwareStatus } from './api'
import type { FirmwareStatus, FirmwareTools } from './types'

const status = ref<FirmwareStatus | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

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
    status.value = await fetchFirmwareStatus()
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
    <div v-if="loading" class="font-mono text-xs">Loading firmware status…</div>
    <div v-else-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <template v-else-if="status">
      <div class="flex items-center justify-between gap-2">
        <span class="font-bold">Host · {{ status.host.state ?? 'unknown' }}</span>
        <span class="font-mono text-xs">{{ status.host.version ?? '—' }}</span>
      </div>

      <div v-if="status.mcus.length" class="space-y-1.5">
        <div
          v-for="mcu in status.mcus"
          :key="mcu.name"
          class="flex items-center justify-between gap-2 rounded-brutal border-2 border-ink px-2 py-1"
        >
          <span class="min-w-0 flex-1 truncate font-bold">{{ mcu.name }}</span>
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
      </div>
      <p v-else class="font-mono text-xs opacity-70">
        {{ status.reachable ? 'No MCUs reported.' : 'Printer not reachable.' }}
      </p>

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

      <p class="font-mono text-[10px] opacity-60">
        Read-only status · configure, build & flash coming next.
      </p>
    </template>
  </div>
</template>
